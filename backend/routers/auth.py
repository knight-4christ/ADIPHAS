from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks  # type: ignore[import-untyped]
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

import os
import logging
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel

logger = logging.getLogger(__name__)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "581777295975-3e074nkevgksedf84k61fg9e8kutfn13.apps.googleusercontent.com")

class GoogleAuthPayload(BaseModel):
    id_token: str

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
def register(request: Request, user: schemas.UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        db_user = db.query(models.User).filter(models.User.username == user.username).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Username already registered")
            
        if user.email:
            db_email = db.query(models.User).filter(models.User.email == user.email).first()
            if db_email:
                raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_pwd = auth_utils.get_password_hash(user.password)
        # Validate role: only CITIZEN and EXPERT are self-assignable.
        # ADMIN must be granted manually via the database or admin panel.
        allowed_roles = {"CITIZEN", "EXPERT"}
        assigned_role = user.role.upper() if user.role and user.role.upper() in allowed_roles else "CITIZEN"
        
        # Generate Verification Token
        import uuid
        verification_token = str(uuid.uuid4()) if user.email else None
        
        new_user = models.User(
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=assigned_role,
            location_lga=user.location_lga,
            genotype=user.genotype,
            blood_group=user.blood_group,
            hashed_password=hashed_pwd,
            email_verification_token=verification_token,
            is_email_verified=False # Now properly defaults to False, verified in background
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        # Background Email Verification using Resend HTTP API
        if user.email:
            def background_verify_and_welcome(user_id: int, user_email: str, user_name: str):
                from backend.core.email_utils import send_email
                from backend.database import SessionLocal
                import logging
                logger = logging.getLogger("adiphas_backend")

                logger.info(f"[Auth] Starting background verification via Resend for {user_email}")
                subject = "Welcome to ADIPHAS Health Intelligence"
                html_content = f"""
                <html><body>
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #0284c7;">Welcome to ADIPHAS, {user_name}!</h2>
                    <p>Your email has been successfully registered and verified for ADIPHAS alerts.</p>
                    <p>You are now enrolled in the automated intelligence engine. You will automatically receive 2-hour situational health briefings and critical outbreak alerts for your area.</p>
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                    <p style="font-size: 12px; color: #888;">This is an automated message. Please do not reply.</p>
                </div>
                </body></html>
                """
                
                try:
                    success = send_email(user_email, subject, html_content)
                    if success:
                        db_session = SessionLocal()
                        try:
                            u = db_session.query(models.User).filter(models.User.id == user_id).first()
                            if u:
                                u.is_email_verified = True
                                db_session.commit()
                                logger.info(f"[Auth] Background verification successful for user {user_name}.")
                        except Exception as e:
                            logger.error(f"[Auth] Error updating user verification status: {e}")
                        finally:
                            db_session.close()
                    else:
                        logger.warning(f"[Auth] send_email returned False for {user_email}")
                except Exception as e:
                    logger.error(f"[Auth] Exception in background task: {e}")

            # Use FastAPI native BackgroundTasks
            background_tasks.add_task(background_verify_and_welcome, new_user.id, user.email, user.username)
                
        return new_user
    except HTTPException:
        raise  # Re-raise known HTTP errors (400 username taken, etc.)
    except Exception as e:
        import logging, traceback
        logging.getLogger(__name__).error(f"Registration error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@router.post("/api/auth/resend-verification")
def resend_verification(background_tasks: BackgroundTasks, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.is_email_verified:
        return {"msg": "Email already verified."}
    
    if not current_user.email:
        raise HTTPException(status_code=400, detail="Account has no email address.")
        
    import uuid
    token = str(uuid.uuid4())
    current_user.email_verification_token = token
    db.commit()
    
    from backend.core.email_utils import send_verification_email
    import os
    backend_url = os.getenv("BACKEND_URL", "https://adiphas.onrender.com")
    
    try:
        background_tasks.add_task(send_verification_email, current_user.email, current_user.username, token, backend_url)
    except Exception:
        pass
        
    return {"msg": "Verification email resent."}

@router.get("/api/auth/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email_verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token.")
    
    user.is_email_verified = True
    user.email_verification_token = None
    db.commit()
    
    import os
    from fastapi.responses import RedirectResponse
    frontend_url = os.getenv("FRONTEND_URL", "https://adiphas.streamlit.app")
    # Redirect to the frontend root page (Command Centre)
    return RedirectResponse(url=frontend_url)

from pydantic import BaseModel
class PasswordResetRequest(BaseModel):
    email_or_username: str

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

@router.post("/api/auth/request-password-reset")
def request_password_reset(payload: PasswordResetRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Generates a password reset token and sends an email."""
    user = db.query(models.User).filter(
        (models.User.email == payload.email_or_username) | 
        (models.User.username == payload.email_or_username)
    ).first()
    
    if not user:
        # Return success anyway to prevent email enumeration attacks
        return {"msg": "If an account exists, a reset link has been sent."}
        
    if not user.email:
        raise HTTPException(status_code=400, detail="Account has no email address associated. Please contact admin.")
        
    import uuid
    token = str(uuid.uuid4())
    user.password_reset_token = token
    db.commit()
    
    from backend.core.email_utils import send_password_reset_email
    import os
    backend_url = os.getenv("BACKEND_URL", "https://adiphas.onrender.com")
    
    try:
        background_tasks.add_task(send_password_reset_email, user.email, user.username, token, backend_url)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not dispatch reset email: {e}")
        
    return {"msg": "If an account exists, a reset link has been sent."}

@router.post("/api/auth/reset-password")
def reset_password(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    """Verifies the reset token and updates the password."""
    user = db.query(models.User).filter(models.User.password_reset_token == payload.token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")
        
    user.hashed_password = auth_utils.get_password_hash(payload.new_password)
    user.password_reset_token = None
    db.commit()
    
    return {"msg": "Password successfully reset."}

@router.post("/api/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth_utils.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = auth_utils.create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/api/auth/google", response_model=schemas.Token)
def google_auth(payload: GoogleAuthPayload, db: Session = Depends(get_db)):
    """Verifies Google ID token and logs in/registers the user."""
    try:
        # 1. Verify the Google ID Token
        id_info = id_token.verify_oauth2_token(
            payload.id_token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        
        email = id_info.get("email")
        full_name = id_info.get("name")
        
        if not email:
            raise HTTPException(status_code=400, detail="Google account has no email.")
            
        # 2. Check if user exists
        user = db.query(models.User).filter(models.User.email == email).first()
        
        if not user:
            # Create new user automatically
            username = email.split("@")[0]
            # Ensure unique username
            orig_username = username
            counter = 1
            while db.query(models.User).filter(models.User.username == username).first():
                username = f"{orig_username}{counter}"
                counter += 1
                
            user = models.User(
                username=username,
                email=email,
                full_name=full_name,
                is_email_verified=True, 
                role="CITIZEN",
                hashed_password="OAUTH_USER_NO_PASSWORD"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
        # 3. Issue ADIPHAS Token
        access_token = auth_utils.create_access_token(data={"sub": user.id})
        return {"access_token": access_token, "token_type": "bearer"}
        
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    except Exception as e:
        logger.error(f"Google Auth Error: {e}")
        raise HTTPException(status_code=500, detail="Authentication failed")

@router.get("/api/auth/google/callback")
def google_callback(request: Request):
    """
    Receives the redirect from Google OAuth implicit flow.
    Google returns the id_token in the URL hash fragment (#id_token=...), which the backend cannot read directly.
    We return a small JS script that extracts it and redirects to the Streamlit frontend.
    """
    frontend_url = os.getenv("FRONTEND_URL", "https://adiphas.streamlit.app")
    
    html_content = f"""
    <html>
        <head><title>Authenticating...</title></head>
        <body style="background-color: #0B1111; color: white; text-align: center; font-family: sans-serif; padding-top: 50px;">
            <h2>Verifying Google Credentials...</h2>
            <script>
                // Extract hash fragment (e.g., #id_token=XYZ&...)
                const hash = window.location.hash.substring(1);
                const params = new URLSearchParams(hash);
                const idToken = params.get('id_token');
                
                if (idToken) {{
                    window.location.href = "{frontend_url}/?g_token=" + idToken;
                }} else {{
                    document.body.innerHTML = "<h2>Google Authentication Failed.</h2><p>No token received. Please go back and try again.</p>";
                }}
            </script>
        </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)

