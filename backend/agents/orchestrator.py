import logging
import json
import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend import models, database
from backend.agents.intelligence.alerting import AlertingEngine
from backend.agents.intelligence.risk import RiskEngine

logger = logging.getLogger(__name__)

class OrchestratorAgent:
    def __init__(self, gemini_model=None):
        self.alerting_engine = AlertingEngine(gemini_model=gemini_model)
        self.risk_engine = RiskEngine(gemini_model=gemini_model)
        self.gemini_model = gemini_model

    def run_predictive_cycle(self, db: Session):
        """Autonomously generates forecasts for all LGA/Disease pairs with enough data."""
        logger.info("Starting Autonomous Predictive Cycle...")
        
        targets = db.query(models.IDSRRecord.lga_code, models.IDSRRecord.disease).distinct().all()
        
        created_count = 0
        for lga_code, disease in targets:
            records = db.query(models.IDSRRecord.cases)\
                .filter(models.IDSRRecord.lga_code == lga_code)\
                .filter(models.IDSRRecord.disease == disease)\
                .order_by(models.IDSRRecord.week_start.asc()).all()
            
            historical_counts = [r[0] for r in records]
            
            if len(historical_counts) >= 4:
                forecast_data, _ = self.alerting_engine.forecast_cases(lga_code, disease, historical_counts)
                is_anom, _ = self.alerting_engine.detect_anomalies(lga_code, disease, historical_counts)
                
                snapshot = db.query(models.PredictiveSnapshot)\
                    .filter(models.PredictiveSnapshot.lga_code == lga_code)\
                    .filter(models.PredictiveSnapshot.disease == disease)\
                    .first()
                
                if not snapshot:
                    snapshot = models.PredictiveSnapshot(lga_code=lga_code, disease=disease)
                    db.add(snapshot)
                
                snapshot.forecast_json = json.dumps(forecast_data)
                snapshot.is_anomaly = is_anom
                snapshot.generated_at = datetime.utcnow()
                created_count += 1
        
        db.commit()
        logger.info(f"Predictive cycle complete. Generated {created_count} snapshots.")

    def run_realtime_intelligence_cycle(self, db: Session):
        """Uses Tavily to fetch live disease outbreak news and store as a snapshot.
        Runs every cycle but only saves a new snapshot every 6 hours to conserve API calls."""
        
        # Check if a recent realtime snapshot exists (within 6 hours)
        last_rt = db.query(models.AutonomousSnapshot)\
            .filter(models.AutonomousSnapshot.snapshot_type == "realtime_intelligence")\
            .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
        
        if last_rt and (datetime.utcnow() - last_rt.generated_at).total_seconds() < 21600:
            logger.info("Realtime intelligence snapshot is still fresh (<6h). Skipping.")
            return
        
        tavily_key = os.getenv("TAVILY_API_KEY")
        if not tavily_key:
            logger.warning("TAVILY_API_KEY not set — realtime intelligence cycle skipped.")
            return
        
        logger.info("Starting Realtime Intelligence Cycle (Tavily)...")
        
        # Targeted disease queries for Lagos/Nigeria
        queries = [
            "disease outbreak Lagos Nigeria 2026",
            "cholera malaria lassa fever Nigeria latest",
            "epidemic health emergency Nigeria today",
        ]
        
        all_results = []
        try:
            import requests
            for query in queries:
                try:
                    payload = {
                        "api_key": tavily_key,
                        "query": query,
                        "search_depth": "basic",
                        "include_answer": False,
                        "max_results": 3
                    }
                    response = requests.post("https://api.tavily.com/search", json=payload, timeout=15)
                    if response.status_code == 200:
                        data = response.json()
                        for r in data.get("results", []):
                            content = r.get("content") or str(r)
                            url = r.get("url", "")
                            all_results.append(f"- {content[:200]} ({url})")
                    else:
                        logger.warning(f"Tavily query failed for '{query}': {response.text}")
                except Exception as e:
                    logger.warning(f"Tavily request error for '{query}': {e}")
        except Exception as global_e:
            logger.error(f"Tavily search execution failed: {global_e}")
            return
        
        if not all_results:
            logger.info("Tavily returned no results. Skipping snapshot.")
            return
        
        # Combine results into a structured intelligence snapshot
        web_intel = "\n".join(all_results[:9])  # Cap at 9 items to control size
        
        # If Gemini is available, summarize; otherwise store raw
        content = web_intel
        if self.gemini_model:
            try:
                from backend.core.model_config import smart_generate
                prompt = f"""Summarize these real-time disease intelligence signals for Lagos/Nigeria (3-5 bullet points, Markdown):
{web_intel}"""
                text, _ = smart_generate(self.gemini_model, prompt, context="RealtimeIntel")
                if text:
                    content = text
            except Exception as e:
                logger.warning(f"AI summarization failed, storing raw: {e}")
        
        snapshot = models.AutonomousSnapshot(
            snapshot_type="realtime_intelligence",
            content=content,
            expires_at=datetime.utcnow() + timedelta(hours=6)
        )
        db.add(snapshot)
        db.commit()
        logger.info(f"Realtime intelligence snapshot saved ({len(all_results)} web signals).")

    def run_briefing_cycle(self, db: Session):
        """Autonomously generates a system-wide intelligence briefing."""
        logger.info("Starting Autonomous Briefing Cycle...")
        
        recent_alerts = db.query(models.EBSAlert).order_by(models.EBSAlert.created_at.desc()).limit(15).all()
        active_anomalies = db.query(models.PredictiveSnapshot).filter(models.PredictiveSnapshot.is_anomaly == True).all()
        
        # Also pull latest Tavily intelligence for richer briefings
        realtime_snap = db.query(models.AutonomousSnapshot)\
            .filter(models.AutonomousSnapshot.snapshot_type == "realtime_intelligence")\
            .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
        
        if not recent_alerts and not active_anomalies and not realtime_snap:
            return

        alert_ctx = "\n".join([f"- {a.disease} in {a.location_text} (Risk: {a.risk_level})" for a in recent_alerts]) if recent_alerts else "None"
        anom_ctx = "\n".join([f"- ANOMALY: {s.disease} in {s.lga_code}" for s in active_anomalies]) if active_anomalies else "None"
        rt_ctx = realtime_snap.content[:500] if realtime_snap else "No web intelligence available"
        
        prompt = f"""Generate a concise situational briefing (Markdown) for health officials.
DB Signals:
{alert_ctx}
Anomalies:
{anom_ctx}
Live Web Intelligence:
{rt_ctx}
Include: 1) Current Landscape 2) Critical Hotspots 3) Recommendation"""
        
        try:
            from backend.core.model_config import smart_generate
            text, model_used = smart_generate(self.gemini_model, prompt, context="BriefingAgent")
            
            if text:
                snapshot = models.AutonomousSnapshot(
                    snapshot_type="daily_briefing",
                    content=text,
                    expires_at=datetime.utcnow() + timedelta(hours=24)
                )
                db.add(snapshot)
                db.commit()
                logger.info("System-wide briefing generated successfully.")
        except Exception as e:
            logger.error(f"Briefing generation failed: {e}")

    def run_auto_verification_cycle(self, db: Session):
        """Autonomously verifies alerts using multi-source cross-referencing."""
        logger.info("Starting Autonomous Verification Cycle...")
        unverified = db.query(models.EBSAlert).filter(models.EBSAlert.verified == False).limit(10).all()
        
        for alert in unverified:
            if alert.source == "Fused Intelligence" and alert.risk_level == "High":
                alert.verified = True
                alert.collected_by = "VerifierAgent (Auto)"
                logger.info(f"Auto-verified high-confidence fused alert: {alert.disease} in {alert.location_text}")
        
        db.commit()
