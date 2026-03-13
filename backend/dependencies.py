import os
import logging
from datetime import datetime
from dotenv import load_dotenv

from google import genai

from backend import models, database
from backend.agents.acquisition.news_scraper import NewsScraperAgent
from backend.agents.acquisition import ingestion
from backend.agents.intelligence import nlp_processor, knowledge_fusion, alerting, risk
from backend.agents.orchestrator import OrchestratorAgent

load_dotenv()

# Configure logger (used everywhere)
logger = logging.getLogger("adiphas_backend")

# Shared System Activities
system_activities = []

def log_activity(agent: str, message: str):
    """Fallback memory-based logging and DB-based logging for system events."""
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

# Initialize Gemini
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

# Initialize Agents
news_agent = NewsScraperAgent()
nlp_agent = nlp_processor.NLPProcessor(gemini_model=gemini_model)
fusion_agent = knowledge_fusion.KnowledgeFusionAgent(gemini_model=gemini_model)
ingestion_agent = ingestion.IngestionAgent()
alerting_engine = alerting.AlertingEngine(gemini_model=gemini_model)
risk_engine = risk.RiskEngine(gemini_model=gemini_model)
orchestrator = OrchestratorAgent(gemini_model=gemini_model)
