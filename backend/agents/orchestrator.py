import logging
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session  # type: ignore[import-untyped]
from backend import models, database  # type: ignore[import-untyped]
from backend.agents.intelligence.alerting import AlertingEngine  # type: ignore[import-untyped]
from backend.agents.intelligence.risk import RiskEngine  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# West Africa Time (UTC+1) for user-facing date strings in briefings
_WAT = timezone(timedelta(hours=1))

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

    def run_realtime_intelligence_cycle(self, db: Session, force: bool = False):
        """Uses Tavily to fetch live disease outbreak news and store as a snapshot.
        Runs every cycle but only saves a new snapshot every 6 hours unless forced."""
        if not force:
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
        
        # Dynamic date-aware queries for Lagos/Nigeria
        now = datetime.utcnow()
        current_year = now.year
        current_month = now.strftime("%B")  # e.g. "April"
        
        queries = [
            f"disease outbreak Lagos Nigeria {current_month} {current_year}",
            f"cholera malaria lassa fever Nigeria latest {current_year}",
            "epidemic health emergency Nigeria today",
        ]
        
        all_results: List[str] = []
        try:
            from langchain_tavily import TavilySearch  # type: ignore[import-untyped]
            web_search = TavilySearch(tavily_api_key=tavily_key, max_results=3)
            
            for query in queries:
                try:
                    raw_response = web_search.invoke(query)
                    # New TavilySearch returns a dict with 'results' key
                    if isinstance(raw_response, dict):
                        results = raw_response.get("results", [])
                    elif isinstance(raw_response, list):
                        results = raw_response
                    else:
                        results = []
                    
                    for r in results:
                        content = r.get("content") or r.get("snippet") or str(r)
                        url = r.get("url", "")
                        all_results.append(f"- {str(content)[:200]} ({url})")  # type: ignore[index]
                except Exception as e:
                    logger.warning(f"Tavily query failed for '{query}': {e}")
        except ImportError:
            logger.error("langchain_tavily not installed — Tavily search unavailable.")
            return
        
        if not all_results:
            logger.info("Tavily returned no results. Skipping snapshot.")
            return
        
        # Combine results into a structured intelligence snapshot
        web_intel = "\n".join(list(all_results)[:9])  # Cap at 9 items to control size  # type: ignore[index]
        
        # If Gemini is available, summarize; otherwise store raw
        content = web_intel
        if self.gemini_model:
            try:
                from backend.core.model_config import smart_generate  # type: ignore[import-untyped]
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
        
        from sqlalchemy.exc import SQLAlchemyError
        try:
            db.add(snapshot)
            db.commit()
        except SQLAlchemyError as e:
            logger.warning(f"DB Connection lost during realtime AI generation: {e}. Recovering...")
            db.rollback()
            db.add(snapshot)
            db.commit()
            
        logger.info(f"Realtime intelligence snapshot saved ({len(all_results)} web signals).")

    def run_briefing_cycle(self, db: Session, force: bool = False):
        """Autonomously generates a system-wide intelligence briefing. Runs every 24h unless forced."""
        if not force:
            # Check for today's briefing
            last_briefing = db.query(models.AutonomousSnapshot)\
                .filter(models.AutonomousSnapshot.snapshot_type == "daily_briefing")\
                .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
            
            if last_briefing and (datetime.utcnow() - last_briefing.generated_at).total_seconds() < 86400:
                logger.info("Daily StAMP briefing is already generated. Skipping.")
                return

        logger.info("Starting Autonomous Briefing Cycle...")
        
        recent_alerts = db.query(models.EBSAlert).order_by(models.EBSAlert.created_at.desc()).limit(15).all()
        active_anomalies = db.query(models.PredictiveSnapshot).filter(models.PredictiveSnapshot.is_anomaly.is_(True)).all()
        
        # Also pull latest Tavily intelligence for richer briefings
        realtime_snap = db.query(models.AutonomousSnapshot)\
            .filter(models.AutonomousSnapshot.snapshot_type == "realtime_intelligence")\
            .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
        
        if not recent_alerts and not active_anomalies and not realtime_snap:
            return

        alert_ctx = "\n".join([f"- {a.disease} in {a.location_text} (Risk: {a.risk_level})" for a in recent_alerts]) if recent_alerts else "None"
        anom_ctx = "\n".join([f"- ANOMALY: {s.disease} in {s.lga_code}" for s in active_anomalies]) if active_anomalies else "None"
        rt_ctx = realtime_snap.content[:500] if realtime_snap else "No web intelligence available"
        prompt = f"""Generate a professional situational briefing (Markdown) for public health officials.
CRITICAL OUTPUT RULES:
- Keep the ENTIRE briefing under 400 words (readable in under 1 minute).
- Use bullet points, bold text, and short paragraphs (max 2 sentences each).
- DO NOT use markdown tables under any circumstances.
- Be detailed and analytical but NEVER verbose — every sentence must carry actionable intelligence.
- Focus on WHAT matters, WHY it matters, and WHAT to do about it.
Today's Date: {datetime.now(_WAT).strftime('%B %d, %Y')}
DB Signals:
{alert_ctx}
Anomalies:
{anom_ctx}
Live Web Intelligence:
{rt_ctx}
Include: 1) Executive Landscape (2-3 bullets) 2) Critical Geo-Hotspots (top 3 only) 3) Key Epidemiological Pattern (1 paragraph) 4) Actionable Recommendations (3-4 bullets)"""
        
        import re
        import time as _time
        
        # Collect source URLs for transparency
        source_urls = []
        if recent_alerts:
            for a in recent_alerts:
                if a.url:
                    source_urls.append(f"- [{a.source}]({a.url})")
        if realtime_snap and realtime_snap.content:
            # Extract URLs from realtime snapshot content
            import re as _re
            urls_found = _re.findall(r'\(https?://[^\)]+\)', realtime_snap.content)
            for u in urls_found[:5]:
                source_urls.append(f"- Web: {u.strip('()')}") 
        
        sources_footer = ""
        if source_urls:
            sources_footer = "\n\n---\n**📚 Intelligence Sources:**\n" + "\n".join(list(set(source_urls))[:10])
        
        # Retry AI generation up to 3 times with cooldowns
        generated_text = None
        model_used = None
        for attempt in range(3):
            try:
                from backend.core.model_config import smart_generate  # type: ignore[import-untyped]
                text, model_used = smart_generate(self.gemini_model, prompt, context="BriefingAgent")
                
                if text:
                    # Sanitize: strip any leaked reasoning traces before storing
                    text = re.sub(r'\[Reasoning\].*?\[Response\]\s*', '', text, flags=re.DOTALL)
                    text = re.sub(r"\[?\{['\"]type['\"]:\s*['\"]reasoning\.text['\"].*?\}\]?", '', text, flags=re.DOTALL)
                    generated_text = text.strip() + sources_footer
                    break
            except Exception as e:
                wait_time = 15 * (attempt + 1)
                logger.warning(f"[BriefingAgent] Attempt {attempt+1}/3 failed ({e}). Retrying in {wait_time}s...")
                _time.sleep(wait_time)
        
        if generated_text:
            snapshot = models.AutonomousSnapshot(
                snapshot_type="daily_briefing",
                content=generated_text,
                expires_at=datetime.utcnow() + timedelta(hours=24)
            )
            from sqlalchemy.exc import SQLAlchemyError
            try:
                db.add(snapshot)
                db.commit()
            except SQLAlchemyError as e:
                logger.warning(f"DB Connection lost during AI briefing generation: {e}. Recovering...")
                db.rollback()
                db.add(snapshot)
                db.commit()
            logger.info(f"System-wide briefing generated successfully via {model_used}.")
        else:
            # Rule-based fallback — users must NEVER see an empty briefing
            logger.warning("[BriefingAgent] All AI retries failed. Generating rule-based fallback briefing.")
            
            alert_count = len(recent_alerts) if recent_alerts else 0
            anomaly_count = len(active_anomalies) if active_anomalies else 0
            diseases_seen = set(a.disease for a in recent_alerts if a.disease) if recent_alerts else set()
            locations_seen = set(a.location_text for a in recent_alerts if a.location_text) if recent_alerts else set()
            high_risk = [a for a in recent_alerts if a.risk_level in ('High', 'Critical')] if recent_alerts else []
            
            fallback_content = f"""## 🛰️ ADIPHAS Intelligence Briefing — {datetime.now(_WAT).strftime('%B %d, %Y')}

**⚠️ AI-powered analysis temporarily unavailable. This is a data-driven summary.**

### Executive Landscape
- **{alert_count}** active disease signals across **{len(locations_seen)}** locations
- **{anomaly_count}** anomalies flagged by predictive engine
- Active diseases under surveillance: **{', '.join(diseases_seen) if diseases_seen else 'None detected'}**

### Critical Signals
"""
            if high_risk:
                for a in high_risk[:5]:
                    fallback_content += f"- 🔴 **{a.disease}** in {a.location_text} — Risk: {a.risk_level}\n"
            else:
                fallback_content += "- No critical-risk signals at this time.\n"
            
            fallback_content += f"\n### Recommendations\n- Continue monitoring local health feeds for emerging patterns.\n- Report unusual symptoms to your nearest health facility.\n- Next AI-powered briefing will be generated in the next monitoring cycle."
            fallback_content += sources_footer
            
            snapshot = models.AutonomousSnapshot(
                snapshot_type="daily_briefing",
                content=fallback_content,
                expires_at=datetime.utcnow() + timedelta(hours=24)
            )
            from sqlalchemy.exc import SQLAlchemyError
            try:
                db.add(snapshot)
                db.commit()
            except SQLAlchemyError as e:
                logger.warning(f"DB Connection lost during AI fallback generation: {e}. Recovering...")
                db.rollback()
                db.add(snapshot)
                db.commit()
            logger.info("Rule-based fallback briefing stored.")

    def run_auto_verification_cycle(self, db: Session):
        """Autonomously verifies alerts using multi-source cross-referencing."""
        logger.info("Starting Autonomous Verification Cycle...")
        unverified = db.query(models.EBSAlert).filter(models.EBSAlert.verified.is_(False)).limit(10).all()
        
        for alert in unverified:
            if alert.source == "Fused Intelligence" and alert.risk_level == "High":
                alert.verified = True
                alert.collected_by = "VerifierAgent (Auto)"
                logger.info(f"Auto-verified high-confidence fused alert: {alert.disease} in {alert.location_text}")
        
        db.commit()
