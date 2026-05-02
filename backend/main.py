import backend.logging_config  # noqa: F401 — must be first to configure logging  # type: ignore[import-untyped]

from fastapi import FastAPI, Depends, HTTPException  # type: ignore[import-untyped]
from fastapi.responses import RedirectResponse  # type: ignore[import-untyped]
from sqlalchemy.orm import Session  # type: ignore[import-untyped]
from sqlalchemy import text  # type: ignore[import-untyped]
from backend import models, database, schemas, auth_utils  # type: ignore[import-untyped]
from backend.database import engine  # type: ignore[import-untyped]
import sys
import os

# Ensure project root is in path for 'backend' module imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.auth_utils import get_password_hash  # type: ignore[import-untyped]
from datetime import datetime, timedelta
from dotenv import load_dotenv  # type: ignore[import-untyped]
load_dotenv()

# Import Core Engine
from backend.core.advisory_engine import AdvisoryEngine  # type: ignore[import-untyped]
from backend.core.vector_store import get_vector_manager  # type: ignore[import-untyped]
from backend.dependencies import (  # type: ignore[import-untyped]
    gemini_model, nlp_agent, logger, system_activities
)
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[import-untyped]
from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]
from google import genai  # type: ignore[import-untyped]
from slowapi import _rate_limit_exceeded_handler  # type: ignore[import-untyped]
from slowapi.errors import RateLimitExceeded  # type: ignore[import-untyped]
from backend.rate_limit import limiter  # type: ignore[import-untyped]



models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="ADIPHAS API", version="1.1.0")

# --- CORS Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Init Core Engine with Gemini
advisory_engine = AdvisoryEngine(gemini_model=gemini_model)
# --- Routers Configuration ---
from backend.routers import advisory, auth, idsr, ebs, system  # type: ignore[import-untyped]

app.include_router(advisory.router)
app.include_router(auth.router)
app.include_router(idsr.router)
app.include_router(ebs.router)
app.include_router(system.router)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Dependencies
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Search router is mounted in advisory
# Auth logic moved to routers/auth.py

# --- Autonomous Monitoring Job ---
from backend.scheduler import start_scheduler, startup_insight_cache  # type: ignore[import-untyped]

@app.on_event("startup")
async def startup_event():
    """Immediately kick off first monitoring cycle and warm up agents on startup."""
    from backend.core.model_config import get_model_status_log
    logger.info(get_model_status_log())
    
    logger.info("ADIPHAS startup — running initial monitoring cycle and data normalization...")
    
    # Start the background scheduling loop & initial insight generation
    await start_scheduler()
    
    logger.info(f"Gemini AI: {'ACTIVE' if gemini_model else 'OFFLINE (no key)'}")
    logger.info(f"spaCy NLP: {'ACTIVE' if nlp_agent.nlp else 'KEYWORD-ONLY MODE'}")
    logger.info("System ready.")

# Apply missing columns for migrations (Safe to run on every boot)
def migrate_database():
    db = database.SessionLocal()
    
    # List of columns that might be missing in production
    cols_to_add = [
        ("is_email_verified", "BOOLEAN DEFAULT FALSE"),
        ("email_verification_token", "VARCHAR"),
        ("password_reset_token", "VARCHAR"),
        ("receive_briefings", "BOOLEAN DEFAULT TRUE")
    ]
    
    logger.info("Running database migration check...")
    for col_name, col_type in cols_to_add:
        try:
            # Check if column exists using information_schema
            check_query = text(f"SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='{col_name}';")
            exists = db.execute(check_query).fetchone()
            
            if not exists:
                logger.warning(f"Migration: Column '{col_name}' is missing. Attempting to add...")
                db.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};"))
                db.commit()
                logger.info(f"Migration: Successfully added '{col_name}'.")
        except Exception as e:
            db.rollback()
            logger.error(f"Migration: Failed to add column '{col_name}': {e}")
            
    db.close()

# Execute migration BEFORE anything else
try:
    migrate_database()
except Exception as e:
    logger.error(f"Critical Migration Failure: {e}")

# Create default admin user on startup if not exists
def create_default_admin():
    db = database.SessionLocal()
    try:
        # Check if users table exists first to avoid crash on brand new DBs
        check_table = db.execute(text("SELECT 1 FROM information_schema.tables WHERE table_name='users';")).fetchone()
        if not check_table:
            logger.warning("Users table does not exist yet. Skipping admin creation.")
            return

        admin = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin:
            hashed_pwd = get_password_hash("admin")
            new_admin = models.User(
                username="admin",
                full_name="System Administrator",
                role="ADMIN",
                hashed_password=hashed_pwd,
                is_email_verified=True # Admin is always verified
            )
            db.add(new_admin)
            db.commit()
            logger.info("Default admin user created.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to check/create default admin: {e}")
    finally:
        db.close()

create_default_admin()

@app.get("/healthcheck")
def healthcheck():
    return {
        "status": "ok", 
        "version": "0.3.1", 
        "spacy_loaded": nlp_agent.nlp is not None,
        "gemini_active": gemini_model is not None
    }

@app.get("/system/model-status")
def get_model_status():
    """Returns the unified model pool status across all providers."""
    from backend.core.model_config import get_model_status  # type: ignore[import-untyped]
    return get_model_status()

@app.get("/system/startup-insight")
def get_startup_insight():
    """Returns the one-time AI insight generated at server startup."""
    return startup_insight_cache

@app.get("/system/token-usage")
def get_token_usage():
    """Returns the running AI token usage across all providers (Gemini + OpenRouter)."""
    from backend.core.token_tracker import get_session_totals  # type: ignore[import-untyped]
    return get_session_totals()

@app.get("/system/briefing")
def get_latest_briefing(db: Session = Depends(get_db)):
    """Returns the most recent system-wide autonomous briefing."""
    import re
    briefing = db.query(models.AutonomousSnapshot)\
        .filter(models.AutonomousSnapshot.snapshot_type == "daily_briefing")\
        .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
    
    if briefing and briefing.content:
        content = briefing.content
        # Strip leaked reasoning blocks: [Reasoning]...[Response] pattern
        content = re.sub(r'\[Reasoning\].*?\[Response\]\s*', '', content, flags=re.DOTALL)
        # Strip raw JSON reasoning objects like [{'type': 'reasoning.text', ...}]
        content = re.sub(r"\[?\{['\"]type['\"]:\s*['\"]reasoning\.text['\"].*?\}\]?", '', content, flags=re.DOTALL)
        briefing.content = content.strip()
    
    return briefing

# --- Security Dependencies ---

# Auth dependencies moved to routers/auth.py

@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirect root to API documentation."""
    return RedirectResponse(url="/docs")

@app.get("/system/activity")
def get_system_activity(limit: int = 50, db: Session = Depends(get_db)):
    """Returns recent system activities from the db for the live log."""
    activities = db.query(models.SystemActivity).order_by(models.SystemActivity.timestamp.desc()).limit(limit).all()
    # Return in chronological order for the UI
    return [{"timestamp": str(a.timestamp), "agent": a.agent, "message": a.message} for a in reversed(activities)]

@app.get("/system/activity/history")
def get_system_activity_history(date_str: str, db: Session = Depends(get_db)):
    """Returns activities for a specific date (YYYY-MM-DD)."""
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        next_date = target_date + timedelta(days=1)
        
        activities = db.query(models.SystemActivity)\
            .filter(models.SystemActivity.timestamp >= target_date)\
            .filter(models.SystemActivity.timestamp < next_date)\
            .order_by(models.SystemActivity.timestamp.asc()).all()
            
        return [{"timestamp": str(a.timestamp), "agent": a.agent, "message": a.message} for a in activities]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

# End of API definitions. See routers/ for modular endpoints.


# Evaluation logic moved to routers/system.py

