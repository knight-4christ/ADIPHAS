from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from . import models, database, schemas, auth_utils
from .database import engine
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
import sys
import os
import asyncio
import uvicorn
import io
import json
import time

# Ensure project root is in path for 'backend' module imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .auth_utils import get_password_hash
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

# Import new agents
from backend.agents.acquisition.news_scraper import NewsScraperAgent
from backend.agents.acquisition import ingestion
from backend.agents.intelligence import nlp_processor, knowledge_fusion, alerting, risk
# Import Core Engine
from backend.core.advisory_engine import AdvisoryEngine
from backend.core.vector_store import get_vector_manager
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from google import genai
import threading

# Configure logging to both file and console
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "adiphas_agent.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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

# --- Gemini Initialization ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_model = None
if GEMINI_API_KEY:
    try:
        gemini_model = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini 2.0 Flash initialized successfully.")
    except Exception as e:
        logger.error(f"Gemini initialization failed: {e}")
else:
    logger.warning("GEMINI_API_KEY not set — AI augmentation disabled.")

# Init Core Engine with Gemini
advisory_engine = AdvisoryEngine(gemini_model=gemini_model)

# Dependencies
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/api/advisory/symptom_check")
def check_symptoms(payload: dict):
    """Analyzes symptoms using the Core Advisory Engine."""
    symptoms = payload.get("symptoms", [])
    duration = payload.get("duration_days", 1)
    result = advisory_engine.analyze_symptoms(symptoms, duration)
    return result

@app.post("/api/advisory/wellness_check")
def check_wellness(payload: dict):
    """Analyzes vitals (BP) using the Core Advisory Engine."""
    sys = payload.get("systolic")
    dia = payload.get("diastolic")
    if sys is None or dia is None:
        return {"status": "Error", "advice": "Please provide both systolic and diastolic values."}
    result = advisory_engine.analyze_wellness(int(sys), int(dia))
    return result

# Initialize Agents — all with Gemini model injected
news_agent = NewsScraperAgent()
nlp_agent = nlp_processor.NLPProcessor(gemini_api_key=GEMINI_API_KEY)
fusion_agent = knowledge_fusion.KnowledgeFusionAgent(gemini_model=gemini_model)
ingestion_agent = ingestion.IngestionAgent()
alerting_engine = alerting.AlertingEngine(gemini_model=gemini_model)
risk_engine = risk.RiskEngine(gemini_model=gemini_model)

# System Activity Log (Memory fallback, primary is DB)
system_activities = []

@app.get("/api/advisory/search")
def advisory_search(query: str, k: int = 3):
    """
    Hybrid RAG Search: ChromaDB first, then Tavily.
    """
    vm = get_vector_manager()
    result = vm.hybrid_search(query, k=k)
    return result

def log_activity(agent, message):
    act = {"timestamp": datetime.now().replace(microsecond=0), "agent": agent, "message": message}
    system_activities.append(act)
    if len(system_activities) > 50:
        system_activities.pop(0)
    logger.info(f"[{agent}] {message}")
    
    # Persist to database
    db = database.SessionLocal()
    try:
        db_activity = models.SystemActivity(
            timestamp=act["timestamp"],
            agent=agent,
            message=message
        )
        db.add(db_activity)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to persist activity log: {e}")
    finally:
        db.close()

# Auth configuration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# --- Autonomous Monitoring Job ---
def autonomous_monitoring_job():
    """
    Background job that runs every 4 hours to scrape news and extract alerts.
    """
    logger.info(f"[{datetime.now().replace(microsecond=0)}] Autonomous Agent waking up to scan for outbreaks...")
    db = database.SessionLocal()
    try:
        logger.info("Starting Autonomous Monitoring Cycle...")
        log_activity("AutonomousAgent", "Waking up to scan for outbreaks...")
        
        # 1. Acquire News Intelligence (scrape returns (results, trace))
        try:
            headlines, scrape_trace = news_agent.scrape()
            sources_hit = set(h.get('source') for h in headlines if h.get('source'))
            sources_str = ", ".join(sources_hit) if sources_hit else "None"
            log_activity("SCOUT", f"Scraped {len(headlines)} articles. Sources: {sources_str}")
            
            # Log exact scraper trace to db
            for st in scrape_trace:
                if st.get('level') == 'info':
                    log_activity("SCOUT", st.get('step'))
                
            # Filter out already existing URLs (DEDUPLICATION LOGIC)
            filtered_headlines = []
            skipped_count = 0
            for item in headlines:
                url = item.get('url')
                if not url:
                    # Fallback to headline text dedupe if no URL provided by scraper
                    exists = db.query(models.EBSAlert).filter(models.EBSAlert.text == item['title']).first()
                else:
                    exists = db.query(models.EBSAlert).filter(models.EBSAlert.url == url).first()
                
                if exists:
                    skipped_count += 1
                else:
                    filtered_headlines.append(item)
            
            if skipped_count > 0:
                log_activity("IntelligenceEngine", f"Skipped {skipped_count} previously processed articles.")
                
            headlines = filtered_headlines
                
        except Exception as e:
            log_activity("SCOUT", f"Scraping failed: {e}")
            headlines = []
            
        # 1.5 Batching (Increased limit as processing is now LOCAL)
        batch_limit = 50 
        new_count = len(headlines)
        if new_count > batch_limit:
            log_activity("IntelligenceEngine", f"Batching: Processing top {batch_limit} out of {new_count} new articles.")
            headlines = headlines[:batch_limit]
        
        # Group reports for fusion (Now LOCAL and INSTANT)
        pending_reports = []
        for item in headlines:
            entities, nlp_trace = nlp_agent.extract_entities(str(item['title']))
            
            if entities['diseases'] and entities['locations']:
                for disease in entities['diseases']:
                    for location in entities['locations']:
                        pending_reports.append({
                            "source": item['source'],
                            "url": item.get('url'),
                            "disease": disease,
                            "location": location,
                            "cases": 1, # Minimal observation
                            "text": item['title'],
                            "timestamp": item['timestamp']
                        })
        
        if pending_reports:
            log_activity("IntelligenceEngine", f"Fusing {len(pending_reports)} candidate reports...")
            groups = {}
            for r in pending_reports:
                key = f"{r['disease']}_{r['location']}"
                if key not in groups: groups[key] = []
                groups[key].append(r)

            for key, group in groups.items():
                result, f_trace = fusion_agent.fuse_reports(group)
                if result and result.get('confidence_score', 0) > 0.4:
                    alert = models.EBSAlert(
                        source="Fused Intelligence",
                        url=result.get('url'),
                        text=f"Confirmed {result['disease']} activity in {result['location']}",
                        timestamp=datetime.now().replace(microsecond=0),
                        location_text=result['location'],
                        disease=result.get('disease'),  # Fixed: was missing
                        collected_by="AutonomousAgent",
                        verified=False,
                        risk_level="High" if result.get('severity_score', 0) > 0.7 or result['confidence_score'] > 0.8 else ("Medium" if result['confidence_score'] > 0.5 else "Low")
                    )
                    db.add(alert)
                    log_activity("AlertingEngine", f"Fused alert: {result['disease']} in {result['location']} (confidence={result['confidence_score']:.2f})")
        else:
            # No dual-entity headlines — save disease-only articles as raw signals
            saved_raw = 0
            for item in headlines:
                entities, _ = nlp_agent.extract_entities(str(item['title']))
                
                diseases = entities.get('diseases', [])
                locations = entities.get('locations', [])
                # Save if at least a disease is found (location defaults to 'Lagos')
                if diseases:
                    alert = models.EBSAlert(
                        source=item.get('source', 'NewsScout'),
                        url=item.get('url'),
                        text=item['title'],
                        timestamp=item.get('timestamp') or datetime.now().replace(microsecond=0),
                        location_text=locations[0] if locations else 'Lagos',
                        disease=diseases[0],
                        collected_by="AutonomousAgent",
                        verified=False,
                        risk_level="Low"
                    )
                    db.add(alert)
                    saved_raw += 1
            if saved_raw:
                log_activity("AlertingEngine", f"Saved {saved_raw} new raw disease signals to EBS database.")
        
        db.commit()
        
        # 3. Vectorize verified alerts for RAG
        try:
            vm = get_vector_manager()
            new_docs = vm.ingest_ebs_alerts(db)
            if new_docs:
                log_activity("VectorEngine", f"Ingested {new_docs} text chunks into ChromaDB.")
        except Exception as e:
            logger.error(f"Vector ingestion failed: {e}")
            
        log_activity("AutonomousAgent", "Monitoring cycle complete.")
    except Exception as e:
        log_activity("System", f"Error in monitoring job: {str(e)}")
        db.rollback()
    finally:
        db.close()

# Initialize and start the scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(autonomous_monitoring_job, 'interval', minutes=15)
scheduler.start()
logger.info("Background Scheduler started.")

# Global startup insight cache
startup_insight_cache = {"insight": None, "generated_at": None}

@app.on_event("startup")
async def startup_event():
    """Immediately kick off first monitoring cycle and warm up agents on startup."""
    logger.info("ADIPHAS startup — running initial monitoring cycle and data normalization...")
    
    # Self-healing: Ensure no 'T' separators in DB timestamps (SQLite compatibility)
    db = database.SessionLocal()
    try:
        from sqlalchemy import text
        db.execute(text("UPDATE ebs_alerts SET timestamp = REPLACE(timestamp, 'T', ' ') WHERE timestamp LIKE '%T%'"))
        db.execute(text("UPDATE ebs_alerts SET created_at = REPLACE(created_at, 'T', ' ') WHERE created_at LIKE '%T%'"))
        
        # --- Add is_vectorized column if it doesn't exist (migration) ---
        try:
            db.execute(text("ALTER TABLE ebs_alerts ADD COLUMN is_vectorized BOOLEAN DEFAULT 0"))
            logger.info("Migration: Added is_vectorized column to ebs_alerts.")
        except Exception:
            pass  # Column already exists
        
        db.commit()
    except Exception as e:
        logger.warning(f"Self-healing cleanup skipped: {e}")
    finally:
        db.close()

    # --- STARTUP-ONLY Gemini Insight (deferred — runs in background after 30s) ---
    def _generate_startup_insight():
        """Deferred startup insight: waits 30s for rate limits to clear, then retries."""
        import time
        time.sleep(30)  # Let the system settle and avoid rate limits
        
        for attempt in range(3):
            try:
                db2 = database.SessionLocal()
                recent_alerts = db2.query(models.EBSAlert).order_by(models.EBSAlert.timestamp.desc()).limit(10).all()
                db2.close()
                
                if not recent_alerts:
                    startup_insight_cache["insight"] = "System just launched — no prior intelligence signals found. The autonomous monitoring cycle will begin gathering data shortly."
                    startup_insight_cache["generated_at"] = datetime.now().replace(microsecond=0).isoformat()
                    return
                
                if gemini_model:
                    alert_summary = "\n".join([f"- {a.disease} in {a.location_text} (Risk: {a.risk_level})" for a in recent_alerts[:5]])
                    prompt = f"""You are ADIPHAS Intelligence. Provide a concise (3 sentence max) "So Far..." startup briefing summarizing the current health intelligence landscape based on these recent signals:
{alert_summary}
Focus on: What patterns are emerging? Any immediate concerns? What should be monitored closely?"""
                    from backend.core.model_config import smart_generate
                    text, model_used = smart_generate(gemini_model, prompt, context="StartupInsight")
                    
                    if text:
                        startup_insight_cache["insight"] = text
                        startup_insight_cache["generated_at"] = datetime.now().replace(microsecond=0).isoformat()
                        logger.info(f"[StartupInsight] Generated successfully using {model_used}.")
                        return
                    else:
                        raise Exception("All models failed for StartupInsight")
                else:
                    # No Gemini — generate a rule-based summary
                    diseases = set(a.disease for a in recent_alerts if a.disease)
                    locations = set(a.location_text for a in recent_alerts if a.location_text)
                    startup_insight_cache["insight"] = f"Monitoring {len(recent_alerts)} recent signals across {len(locations)} locations. Active diseases: {', '.join(diseases) or 'General health'}. System is gathering intelligence."
                    startup_insight_cache["generated_at"] = datetime.now().replace(microsecond=0).isoformat()
                    return
                    
            except Exception as e:
                wait_time = 15 * (attempt + 1)
                logger.warning(f"[StartupInsight] Attempt {attempt+1}/3 failed ({e}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
        
        # All retries failed — fallback to rule-based summary
        try:
            db3 = database.SessionLocal()
            count = db3.query(models.EBSAlert).count()
            db3.close()
            startup_insight_cache["insight"] = f"AI briefing temporarily unavailable (rate limit). The system has {count} alerts in database and is actively monitoring."
            startup_insight_cache["generated_at"] = datetime.now().replace(microsecond=0).isoformat()
        except:
            startup_insight_cache["insight"] = "AI briefing deferred. Intelligence gathering is underway."
            startup_insight_cache["generated_at"] = datetime.now().replace(microsecond=0).isoformat()
    
    threading.Thread(target=_generate_startup_insight, daemon=True).start()

    threading.Thread(target=autonomous_monitoring_job, daemon=True).start()
    logger.info(f"Gemini AI: {'ACTIVE' if gemini_model else 'OFFLINE (no key)'}")
    logger.info(f"spaCy NLP: {'ACTIVE' if nlp_agent.nlp else 'KEYWORD-ONLY MODE'}")
    logger.info("System ready.")

# Create default admin user on startup if not exists
def create_default_admin():
    db = database.SessionLocal()
    try:
        admin = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin:
            hashed_pwd = get_password_hash("admin")
            new_admin = models.User(
                username="admin",
                full_name="System Administrator",
                role="ADMIN",
                hashed_password=hashed_pwd
            )
            db.add(new_admin)
            db.commit()
            logger.info("Default admin user created.")
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
    """Returns the current Gemini model fallback status."""
    from backend.core.model_config import get_model_status
    return get_model_status()

@app.get("/system/startup-insight")
def get_startup_insight():
    """Returns the one-time AI insight generated at server startup."""
    return startup_insight_cache

@app.get("/system/token-usage")
def get_token_usage():
    """Returns the running Gemini token usage for this server session."""
    from backend.core.token_tracker import get_session_totals
    return get_session_totals()

@app.get("/system/metrics")
def get_system_metrics(db: Session = Depends(get_db)):
    """Returns today's scraping and intelligence metrics from the activity log."""
    from sqlalchemy import func, cast, Date
    today = datetime.now().date()
    
    # Count today's activities by agent
    activities = db.query(
        models.SystemActivity.agent,
        func.count(models.SystemActivity.id).label("count")
    ).filter(
        cast(models.SystemActivity.timestamp, Date) == today
    ).group_by(models.SystemActivity.agent).all()
    
    metrics = {a.agent: a.count for a in activities}
    
    # Count total alerts in DB
    total_alerts = db.query(func.count(models.EBSAlert.alert_id)).scalar()
    verified_alerts = db.query(func.count(models.EBSAlert.alert_id)).filter(models.EBSAlert.verified == True).scalar()
    
    # --- Scraping Metrics (from most recent SCOUT activity) ---
    import re
    scout_activities = db.query(models.SystemActivity).filter(
        models.SystemActivity.agent == "SCOUT",
        cast(models.SystemActivity.timestamp, Date) == today
    ).order_by(models.SystemActivity.timestamp.desc()).all()
    
    last_scrape_count = 0
    last_scrape_sources = ""
    for sa in scout_activities:
        m = re.search(r'Scraped (\d+) articles?\. Sources: (.+)', sa.message)
        if m:
            last_scrape_count = int(m.group(1))
            last_scrape_sources = m.group(2)
            break
    
    # Articles processed/skipped from IntelligenceEngine
    intel_activities = db.query(models.SystemActivity).filter(
        models.SystemActivity.agent == "IntelligenceEngine",
        cast(models.SystemActivity.timestamp, Date) == today
    ).order_by(models.SystemActivity.timestamp.desc()).all()
    
    articles_skipped = 0
    articles_batched = 0
    for sa in intel_activities:
        m_skip = re.search(r'Skipped (\d+)', sa.message)
        if m_skip:
            articles_skipped = int(m_skip.group(1))
        m_batch = re.search(r'Processing top (\d+) out of (\d+)', sa.message)
        if m_batch:
            articles_batched = int(m_batch.group(2))
    
    # Alerts saved today
    alerts_saved_msg = [sa for sa in db.query(models.SystemActivity).filter(
        models.SystemActivity.agent == "AlertingEngine",
        cast(models.SystemActivity.timestamp, Date) == today
    ).all()]
    alerts_saved_today = len(alerts_saved_msg)
    
    return {
        "today_activity_by_agent": metrics,
        "total_alerts_in_db": total_alerts,
        "verified_alerts": verified_alerts,
        # Scraping Metrics
        "last_scrape_articles": last_scrape_count,
        "last_scrape_sources": last_scrape_sources,
        "articles_skipped": articles_skipped,
        "articles_new": articles_batched if articles_batched else max(0, last_scrape_count - articles_skipped),
        "alerts_saved_today": alerts_saved_today,
        "last_updated": datetime.now().replace(microsecond=0).isoformat()
    }

# --- Dependencies (using get_db defined above) ---

# --- Security Dependencies ---

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
        if user.role == "ADMIN":
            return user
        if role == "EXPERT" and user.role == "EXPERT":
            return user
        if user.role == role:
            return user
        raise HTTPException(status_code=403, detail="Operation not permitted")
    return role_checker

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

# --- Authentication Endpoints ---

@app.get("/users/me", response_model=schemas.UserOut)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user

@app.put("/users/profile", response_model=schemas.UserOut)
def update_profile(profile_update: schemas.UserBase, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    for var, value in vars(profile_update).items():
        if value is not None:
            setattr(current_user, var, value)
    db.commit()
    db.refresh(current_user)
    return current_user

@app.get("/users/list", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), current_user: models.User = Depends(check_role("ADMIN"))):
    return db.query(models.User).all()

@app.delete("/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(check_role("ADMIN"))):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cant delete yourself")
    
    user_to_delete = db.query(models.User).filter(models.User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user_to_delete)
    db.commit()
    return {"status": "success", "message": f"User {user_id} removed"}


# --- Authentication Endpoints ---

@app.post("/auth/register", response_model=schemas.UserOut)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_pwd = auth_utils.get_password_hash(user.password)
    new_user = models.User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        location_lga=user.location_lga,
        genotype=user.genotype,
        blood_group=user.blood_group,
        hashed_password=hashed_pwd
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth_utils.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = auth_utils.create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}


# --- Data Acquisition Endpoints ---

@app.post("/idsr/upload")
def upload_idsr(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = file.file.read()
    result = ingestion_agent.process_idsr_csv(content, db)
    return result

# NOTE: /idsr/history endpoint is defined below (near line 826) with full field set

@app.get("/acquisition/news/scrape")
def scrape_news():
    """
    Triggers the NewsScraperAgent to fetch health headlines.
    """
    try:
        headlines, trace = news_agent.scrape()  # Fixed: was scrape_headlines()
        
        # Process with NLP
        processed_data = []
        for item in headlines:
            entities, nlp_trace = nlp_agent.extract_entities(item['title'])
            processed_data.append({
                "raw": item,
                "extracted": entities
            })
            # Merge NLP trace into main trace with context
            for t in nlp_trace:
                t['step'] = f"[NLP] {t['step']}"
            trace.extend(nlp_trace)
            
        return {"status": "success", "count": len(processed_data), "data": processed_data, "trace": trace}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Intelligence Endpoints ---

@app.post("/intelligence/fuse")
def fuse_intelligence(reports: List[dict]):
    """
    Fuses conflicting reports using the KnowledgeFusionAgent.
    """
    try:
        result, trace = fusion_agent.fuse_reports(reports)
        if not result:
            return {"status": "no_consensus", "trace": trace}
        return result | {"trace": trace} # Merge trace into result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/intelligence/sources")
def get_intelligence_sources():
    """Returns the list of monitored epidemiological sources and their reliability weights."""
    return fusion_agent.get_source_registry()

@app.post("/ebs/ingest", response_model=schemas.EBSAlertResponse)
def ingest_ebs(alert: schemas.EBSAlertCreate, db: Session = Depends(get_db)):
    db_alert = models.EBSAlert(**alert.model_dump())
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert

@app.post("/symptom/assess", response_model=schemas.PHASNote)
def assess_symptoms(payload: schemas.SymptomPayload, db: Session = Depends(get_db)):
    # Fetch user for biodata and contribution tracking
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.contributions += 1
    user.impact_score += 10 # Base points for engaging
    db.commit()

    # 1. NLP Deep Analysis (Disease Inference)
    symptom_text = ", ".join(payload.symptoms) if payload.symptoms else ""
    nlp_results, nlp_trace = nlp_agent.extract_entities(symptom_text)
    detected_disease = nlp_results['diseases'][0] if nlp_results['diseases'] else None
    
    # 2. Environmental & Trending Risk Integration
    active_alerts = db.query(models.EBSAlert).all()
    env_penalty, env_trace = risk_engine.compute_environmental_risk_enhanced(user.location_lga or "Unknown", active_alerts)
    
    # 3. Personalized Advisory (with disease context)
    advisories = risk_engine.get_personalized_advisory(user.genotype, user.blood_group, detected_disease=detected_disease)
    
    # 4. Final Risk Calculation
    # Base risk derived from symptoms + NLP severity + Environmental Context
    base_risk = 0.2 if payload.symptoms else 0.0
    nlp_bonus = nlp_results.get('severity_score', 0) * 0.3 # Scale NLP severity impact
    
    final_risk_score = min(1.0, base_risk + nlp_bonus + (env_penalty / 100.0))
    
    # Fixed: interpret_risk_score returns a dict, not a tuple
    risk_result = risk_engine.interpret_risk_score(final_risk_score * 100)
    risk_category = risk_result.get("category", "Low")
    category_trace = risk_result.get("trace", [])

    # Combine all traces for transparency
    full_trace = nlp_trace + env_trace + category_trace

    # 5. Hybrid RAG Advisory — fetch context from local DB + Tavily, then ask Gemini
    ai_clinical_insight = None
    ai_situational_summary = None
    if payload.symptoms:
        try:
            vm = get_vector_manager()
            search_query = f"Disease outbreaks and protocols for {', '.join(payload.symptoms)} in {user.location_lga or 'Lagos'} Nigeria"
            rag_result = vm.hybrid_search(search_query, k=3)
            
            # Build context string from RAG results
            rag_context_parts = []
            for r in rag_result.get("results", [])[:3]:
                content = r.get("content") or r.get("snippet") or str(r)
                rag_context_parts.append(content[:300])
            context_str = "\n".join(rag_context_parts) if rag_context_parts else ""
            
            # Pass enriched context to Gemini
            ai_clinical_insight = advisory_engine.analyze_with_ai(
                payload.symptoms, payload.duration_days, context_str=context_str
            )
            full_trace.append({"step": f"Hybrid RAG: Used {rag_result.get('source', 'unknown')} context ({len(rag_context_parts)} chunks) for AI advisory.", "timestamp": datetime.now().replace(microsecond=0)})
        except Exception as e:
            logger.error(f"Hybrid RAG advisory failed: {e}")

    # Risk interpretation with AI augmentation
    if gemini_model:
        risk_result_ai = risk_engine.interpret_risk_score(
            final_risk_score * 100,
            user_traits={"genotype": user.genotype, "blood_group": user.blood_group},
            active_alerts=active_alerts[:5]
        )
        ai_situational_summary = risk_result_ai.get("ai_situational_summary")

    return {
        "user_id": payload.user_id,
        "date": datetime.now().date(),
        "risk_score": final_risk_score,
        "suggestions": advisories + ["Monitor symptoms (fever/pain)", "Stay hydrated"],
        "tracking_plan": ["Monitor temperature every 6 hours", "Update health profile if symptoms change"],
        "risk_category": risk_category,
        "ai_clinical_insight": ai_clinical_insight,
        "ai_situational_summary": ai_situational_summary,
        "trace": full_trace
    }

@app.post("/predict/forecast", response_model=schemas.PredictionReport)
def predict_forecast(request: schemas.PredictionRequest, db: Session = Depends(get_db)):
    # --- Real Data Strategy ---
    # 1. Try IDSR records (structured weekly case counts)
    records = (
        db.query(models.IDSRRecord)
        .filter(
            models.IDSRRecord.lga_code == request.lga_code,
            models.IDSRRecord.disease == request.disease
        )
        .order_by(models.IDSRRecord.week_start)
        .all()
    )
    historical_data = [r.cases for r in records] if len(records) >= 4 else None

    # 2. Fallback: count EBSAlerts per week (real scraped intelligence)
    if not historical_data:
        from sqlalchemy import func, extract
        weekly_counts = (
            db.query(
                func.strftime('%Y-%W', models.EBSAlert.timestamp).label('week'),
                func.count(models.EBSAlert.alert_id).label('count')
            )
            .filter(
                models.EBSAlert.disease == request.disease,
                models.EBSAlert.location_text.ilike(f"%{request.lga_code}%")
            )
            .group_by(func.strftime('%Y-%W', models.EBSAlert.timestamp))
            .order_by(func.strftime('%Y-%W', models.EBSAlert.timestamp))
            .all()
        )
        if len(weekly_counts) >= 4:
            historical_data = [wc.count for wc in weekly_counts]

    forecast, trace = alerting_engine.forecast_cases(
        request.lga_code, request.disease, historical_data=historical_data
    )

    # Handle "insufficient data" gracefully
    if forecast.get("insufficient_data"):
        return {
            "lga_code": request.lga_code,
            "disease": request.disease,
            "week_start": datetime.now().date(),
            "pred_cases": 0, "pred_ci_lower": 0, "pred_ci_upper": 0,
            "anomaly_flag": False,
            "forecast": [], "ci_lower": [], "ci_upper": [],
            "mae": 0.0, "rmse": 0.0,
            "validation_period": "N/A",
            "policy_recommendation_plan": forecast.get("message"),
            "trace": trace
        }

    # Run anomaly detection with real data
    is_anom, _ = alerting_engine.detect_anomalies(request.lga_code, request.disease, historical_data)

    return {
        "lga_code": request.lga_code,
        "disease": request.disease,
        "week_start": datetime.now().date(),
        "pred_cases": forecast["forecast"][0],
        "pred_ci_lower": forecast["ci_lower"][0],
        "pred_ci_upper": forecast["ci_upper"][0],
        "anomaly_flag": is_anom,
        # Extra fields consumed by UI
        "forecast": forecast["forecast"],
        "ci_lower": forecast["ci_lower"],
        "ci_upper": forecast["ci_upper"],
        "mae": forecast["mae"],
        "rmse": forecast["rmse"],
        "validation_period": forecast.get("validation_period", "2 weeks"),
        "policy_recommendation_plan": forecast.get("policy_recommendation_plan"),
        "data_points_used": forecast.get("data_points_used", 0),
        "trace": trace
    }

@app.get("/idsr/history")
def get_idsr_history(lga_code: str = None, disease: str = None, db: Session = Depends(get_db)):
    """Returns raw IDSR weekly records for a given LGA and disease for chart rendering."""
    query = db.query(models.IDSRRecord)
    if lga_code:
        query = query.filter(models.IDSRRecord.lga_code == lga_code)
    if disease:
        query = query.filter(models.IDSRRecord.disease == disease)
    records = query.order_by(models.IDSRRecord.week_start).all()
    return [
        {
            "week_start": str(r.week_start),
            "cases": r.cases,
            "deaths": r.deaths,
            "lga_code": r.lga_code,
            "disease": r.disease,
            "reporting_week": r.reporting_week
        }
        for r in records
    ]


@app.post("/alerts/{alert_id}/verify")
def verify_alert(alert_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(check_role("EXPERT"))):
    alert = db.query(models.EBSAlert).filter(models.EBSAlert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.verified = True
    db.commit()
    log_activity("ExpertManager", f"Alert {alert_id} verified by {current_user.username}")
    return {"status": "verified"}

@app.delete("/alerts/{alert_id}")
def discard_alert(alert_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(check_role("EXPERT"))):
    """Discards/removes an EBS Alert. Requires EXPERT role."""
    alert = db.query(models.EBSAlert).filter(models.EBSAlert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()
    log_activity("ExpertManager", f"Alert {alert_id} discarded by {current_user.username}")
    return {"status": "discarded"}

@app.get("/alerts/list", response_model=List[schemas.EBSAlertResponse])
def list_alerts(db: Session = Depends(get_db)):
    return db.query(models.EBSAlert).all()


# --- Intelligence Briefing Endpoint (with Caching to prevent AI spam) ---
briefing_ai_cache = {}  # Format: {(lga, role): (insight, timestamp)}
CACHE_EXPIRY = timedelta(minutes=10)

@app.get("/intelligence/briefing")
def get_briefing(lga: str = None, role: str = "CITIZEN", db: Session = Depends(get_db)):
    """Returns a contextual health briefing filtered by LGA and user role, with AI insights."""
    query = db.query(models.EBSAlert)
    if lga:
        query = query.filter(models.EBSAlert.location_text.ilike(f"%{lga}%"))
    
    alerts = query.order_by(models.EBSAlert.timestamp.desc()).limit(10).all()
    
    briefing_items = [
        {"text": a.text, "risk_level": a.risk_level, "location": a.location_text,
         "disease": a.disease, "verified": a.verified}
        for a in alerts
    ]

    # Caching Logic
    cache_key = (lga or "Global", role)
    now = datetime.now()
    
    if cache_key in briefing_ai_cache:
        cached_insight, cached_time = briefing_ai_cache[cache_key]
        if now - cached_time < CACHE_EXPIRY:
            return {
                "lga": lga, "role": role, "alerts_count": len(alerts), 
                "briefing": briefing_items, "ai_insight": cached_insight,
                "cached": True
            }

    ai_insight = "Gemini intelligence is currently restricted or offline."
    if gemini_model and alerts:
        try:
            # Context for AI
            summary_alerts = "\n".join([f"- {a.disease} alert in {a.location_text} (Risk: {a.risk_level})" for a in alerts[:5]])
            role_desc = "a resident/citizen" if role == "CITIZEN" else "a public health professional"
            
            prompt = f"""
            You are ADIPHAS AI Intelligence. Provide a concise (max 3 sentences) executive health briefing for {role_desc} in {lga or 'Lagos'}, Nigeria.
            
            Recent Signals:
            {summary_alerts}
            
            Analyze these signals for immediate threats or trends. If the data is sparse, provide a general vigilance advisory.
            """
            from backend.core.model_config import smart_generate
            text, model_used = smart_generate(gemini_model, prompt, context="IntelligenceBriefing")
            
            if text:
                ai_insight = text
                # Update Cache
                briefing_ai_cache[cache_key] = (ai_insight, now)
            else:
                ai_insight = "AI analysis temporarily unavailable across all models."
            
        except Exception as e:
            logger.error(f"Briefing generation failed: {e}")
            ai_insight = "AI analysis encountered a temporary buffer issue. Review raw signals below."

    return {
        "lga": lga, 
        "role": role, 
        "alerts_count": len(alerts), 
        "briefing": briefing_items,
        "ai_insight": ai_insight,
        "cached": False
    }


# --- NLP Extraction Endpoint (for UI evaluation module) ---

@app.post("/api/nlp/extract")
def nlp_extract(payload: dict):
    """Extracts disease/location entities from raw text using the NLP Agent."""
    text = payload.get("text", "")
    entities, trace = nlp_agent.extract_entities(text)
    return {"entities": entities, "trace": trace}


# --- Evaluation Endpoints ---

@app.get("/api/evaluation/metrics")
def get_evaluation_metrics(db: Session = Depends(get_db)):
    """Returns aggregate NLP performance metrics from evaluation samples."""
    samples = db.query(models.EvaluationSample).all()
    f1_scores = [s.f1_score for s in samples if s.f1_score is not None]
    avg_f1 = round(sum(f1_scores) / len(f1_scores), 4) if f1_scores else 0.0
    return {"total_samples": len(samples), "avg_f1": avg_f1}

@app.get("/api/evaluation/samples")
def get_evaluation_samples(db: Session = Depends(get_db)):
    """Returns the last 50 evaluation samples for the audit trail."""
    samples = db.query(models.EvaluationSample).order_by(
        models.EvaluationSample.created_at.desc()
    ).limit(50).all()
    return [
        {
            "id": s.id,
            "raw_text": s.raw_text,
            "expected_entities": s.expected_entities,
            "actual_entities": s.actual_entities,
            "f1_score": s.f1_score if s.f1_score is not None else 0.0,
            "created_at": s.created_at.isoformat() if s.created_at else None
        }
        for s in samples
    ]

@app.post("/api/evaluation/submit")
def submit_evaluation(payload: dict, db: Session = Depends(get_db)):
    """Submits an evaluation sample and computes its F1-score."""
    raw_text = payload.get("raw_text", "")
    expected_str = payload.get("expected_entities", "{}")
    actual_str = payload.get("actual_entities", "{}")

    try:
        expected = json.loads(expected_str)
        actual = json.loads(actual_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in entities fields.")

    # Compute micro-averaged F1 across diseases + locations
    def compute_f1(exp_list, act_list):
        exp_set = set(e.lower() for e in exp_list)
        act_set = set(a.lower() for a in act_list)
        tp = len(exp_set & act_set)
        if tp == 0:
            return 0.0
        precision = tp / len(act_set) if act_set else 0.0
        recall = tp / len(exp_set) if exp_set else 0.0
        return round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0

    disease_f1 = compute_f1(expected.get("diseases", []), actual.get("diseases", []))
    location_f1 = compute_f1(expected.get("locations", []), actual.get("locations", []))
    avg_f1 = round((disease_f1 + location_f1) / 2, 4)

    sample = models.EvaluationSample(
        raw_text=raw_text,
        expected_entities=expected_str,
        actual_entities=actual_str,
        f1_score=avg_f1
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return {"id": sample.id, "f1_score": avg_f1, "disease_f1": disease_f1, "location_f1": location_f1}


