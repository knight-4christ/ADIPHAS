from fastapi import APIRouter, Depends, HTTPException  # type: ignore[import-untyped]
from fastapi.security import OAuth2PasswordRequestForm  # type: ignore[import-untyped]
from sqlalchemy.orm import Session  # type: ignore[import-untyped]
from typing import List

from backend import models, schemas, auth_utils  # type: ignore[import-untyped]
from backend.database import get_db  # type: ignore[import-untyped]
from backend.rate_limit import limiter  # type: ignore[import-untyped]
from fastapi import Request  # type: ignore[import-untyped]

router = APIRouter(tags=["Authentication"])
from jose import JWTError, jwt  # type: ignore[import-untyped]
from fastapi.security import OAuth2PasswordBearer  # type: ignore[import-untyped]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, auth_utils.SECRET_KEY, algorithms=[auth_utils.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

def check_role(role: str):
    def role_checker(user: models.User = Depends(get_current_user)):
        # Role hierarchy: ADMIN > EXPERT > CITIZEN
        role_levels = {"CITIZEN": 1, "EXPERT": 2, "ADMIN": 3}
        user_level = role_levels.get(user.role, 0)
        required_level = role_levels.get(role, 99)
        
        if user_level >= required_level:
            return user
        raise HTTPException(status_code=403, detail="Operation not permitted")
    return role_checker

@router.get("/api/users/me", response_model=schemas.UserOut)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user

@router.put("/api/users/profile", response_model=schemas.UserOut)
def update_profile(profile_update: schemas.UserBase, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Protect sensitive fields from mass assignment
    protected_fields = {"role", "impact_score", "contributions", "username"}
    for var, value in vars(profile_update).items():
        if value is not None and var not in protected_fields:
            setattr(current_user, var, value)
    db.commit()
    db.refresh(current_user)
    return current_user

@router.get("/api/users/list", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), current_user: models.User = Depends(check_role("ADMIN"))):
    return db.query(models.User).all()

@router.delete("/api/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(check_role("ADMIN"))):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cant delete yourself")
    
    user_to_delete = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user_to_delete)
    db.commit()
    return {"status": "success", "message": f"User {user_id} removed"}

@router.post("/api/auth/register", response_model=schemas.UserOut)
@limiter.limit("5/minute") # Protect registration from brute-force
def register(request: Request, user: schemas.UserCreate, db: Session = Depends(get_db)):
    try:
        db_user = db.query(models.User).filter(models.User.username == user.username).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Username already registered")
            
        if user.email:
            db_email = db.query(models.User).filter(models.User.email == user.email).first()
            if db_email:
                raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_pwd = auth_utils.get_password_hash(user.password)
        new_user = models.User(
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role="CITIZEN",
            location_lga=user.location_lga,
            genotype=user.genotype,
            blood_group=user.blood_group,
            hashed_password=hashed_pwd
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Registration crash: {str(e)}\n\n{traceback.format_exc()}")

@router.post("/api/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth_utils.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = auth_utils.create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}
