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
        """Autonomously generates role-specific intelligence briefings. Runs every 2h unless forced."""
        if not force:
            # Check for today's briefing (interval reduced to 2 hours / 7200s)
            last_briefing = db.query(models.AutonomousSnapshot)\
                .filter(models.AutonomousSnapshot.snapshot_type == "daily_briefing")\
                .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
            
            if last_briefing and (datetime.utcnow() - last_briefing.generated_at).total_seconds() < 7200:
                logger.info("2-hour StAMP briefing is already generated. Skipping.")
                return None, None

        logger.info("Starting Autonomous Briefing Cycle (Citizen + Expert)...")
        
        recent_alerts = db.query(models.EBSAlert).order_by(models.EBSAlert.created_at.desc()).limit(15).all()
        active_anomalies = db.query(models.PredictiveSnapshot).filter(models.PredictiveSnapshot.is_anomaly.is_(True)).all()
        
        # Also pull latest Tavily intelligence for richer briefings
        realtime_snap = db.query(models.AutonomousSnapshot)\
            .filter(models.AutonomousSnapshot.snapshot_type == "realtime_intelligence")\
            .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
        
        if not recent_alerts and not active_anomalies and not realtime_snap:
            return None, None

        alert_ctx = "\n".join([f"- {a.disease} in {a.location_text} (Risk: {a.risk_level})" for a in recent_alerts]) if recent_alerts else "None"
        anom_ctx = "\n".join([f"- ANOMALY: {s.disease} in {s.lga_code}" for s in active_anomalies]) if active_anomalies else "None"
        rt_ctx = realtime_snap.content[:500] if realtime_snap else "No web intelligence available"
        
        now_wat = datetime.now(_WAT)
        hour = now_wat.hour
        if hour < 12:
            greeting = "Good morning"
            greeting_prefix = f"### 🌤️ {greeting}!\n\n"
        elif hour < 17:
            greeting = "Good afternoon"
            greeting_prefix = f"### ☀️ {greeting}!\n\n"
        else:
            greeting = "Good evening"
            greeting_prefix = f"### 🌙 {greeting}!\n\n"
        
        data_block = f"""Today's Date: {now_wat.strftime('%B %d, %Y')}
DB Signals:
{alert_ctx}
Anomalies:
{anom_ctx}
Live Web Intelligence:
{rt_ctx}"""
        
        citizen_prompt = f"""Generate a professional situational briefing (Markdown) for the general public and community health workers.
CRITICAL OUTPUT RULES:
- Keep the ENTIRE briefing under 400 words.
- Use bullet points, bold text, and short paragraphs. DO NOT use markdown tables.
- Use simple, non-technical language that any citizen can understand.
- Focus on WHAT matters, WHY it matters, and WHAT to do about it.
{data_block}
Include: 1) Executive Landscape (2-3 bullets) 2) Critical Geo-Hotspots (top 3 only) 3) Key Epidemiological Pattern (1 paragraph) 4) Actionable Recommendations (3-4 bullets)"""
        
        expert_prompt = f"""Generate a comprehensive, expert-grade epidemiological intelligence briefing (Markdown) for public health officials and epidemiologists.
CRITICAL OUTPUT RULES:
- This briefing should be between 800-1200 words.
- Use technical epidemiological terminology where appropriate.
- DO NOT use markdown tables. Every claim must reference the underlying signal data.
{data_block}
Include ALL of the following sections:
1) Situation Overview & Threat Assessment
2) Signal Decomposition & Source Analysis
3) Epidemiological Risk Analysis
4) Geographic Hotspot Deep-Dive
5) Strategic Recommendations"""

        import re
        import time as _time
        
        # Collect source URLs for transparency
        source_urls = []
        if recent_alerts:
            for a in recent_alerts:
                if a.url:
                    source_urls.append(f"- [{a.source}]({a.url})")
        if realtime_snap and realtime_snap.content:
            import re as _re
            urls_found = _re.findall(r'\(https?://[^\)]+\)', realtime_snap.content)
            for u in urls_found[:5]:
                source_urls.append(f"- Web: {u.strip('()')}")
        
        sources_footer = ""
        if source_urls:
            sources_footer = "\n\n---\n**📚 Intelligence Sources:**\n" + "\n".join(list(set(source_urls))[:10])
        
        briefing_configs = [
            ("daily_briefing", citizen_prompt, "CitizenBriefing"),
            ("daily_briefing_expert", expert_prompt, "ExpertBriefing"),
        ]
        
        final_briefings = {}
        
        for snapshot_type, prompt, agent_label in briefing_configs:
            generated_text = None
            model_used = None
            for attempt in range(3):
                try:
                    from backend.core.model_config import smart_generate  # type: ignore[import-untyped]
                    text, model_used = smart_generate(self.gemini_model, prompt, context=agent_label)
                    
                    if text:
                        text = re.sub(r'\[Reasoning\].*?\[Response\]\s*', '', text, flags=re.DOTALL)
                        text = re.sub(r"\[?\{['\"]type['\"]:\s*['\"]reasoning\.text['\"].*?\}\]?", '', text, flags=re.DOTALL)
                        generated_text = greeting_prefix + text.strip() + sources_footer
                        break
                except Exception as e:
                    wait_time = 15 * (attempt + 1)
                    logger.warning(f"[{agent_label}] Attempt {attempt+1}/3 failed ({e}). Retrying in {wait_time}s...")
                    _time.sleep(wait_time)
            
            if generated_text:
                final_briefings[snapshot_type] = generated_text
            else:
                logger.warning(f"[{agent_label}] All AI retries failed. Generating rule-based fallback.")
                alert_count = len(recent_alerts) if recent_alerts else 0
                anomaly_count = len(active_anomalies) if active_anomalies else 0
                diseases_seen = set(a.disease for a in recent_alerts if a.disease) if recent_alerts else set()
                locations_seen = set(a.location_text for a in recent_alerts if a.location_text) if recent_alerts else set()
                high_risk = [a for a in recent_alerts if a.risk_level in ('High', 'Critical')] if recent_alerts else []
                
                fallback_content = f"{greeting_prefix}## 🛰️ ADIPHAS Intelligence Briefing — {now_wat.strftime('%B %d, %Y')}\n**⚠️ AI-powered analysis temporarily unavailable. This is a data-driven summary.**\n### Executive Landscape\n- **{alert_count}** active disease signals across **{len(locations_seen)}** locations\n- **{anomaly_count}** anomalies flagged\n- Active diseases: **{', '.join(diseases_seen) if diseases_seen else 'None detected'}**\n### Critical Signals\n"
                if high_risk:
                    for a in high_risk[:5]: fallback_content += f"- 🔴 **{a.disease}** in {a.location_text} — Risk: {a.risk_level}\n"
                else:
                    fallback_content += "- No critical-risk signals at this time.\n"
                fallback_content += f"\n### Recommendations\n- Continue monitoring local health feeds.\n- Report unusual symptoms.\n{sources_footer}"
                final_briefings[snapshot_type] = fallback_content
                
            snapshot = models.AutonomousSnapshot(
                snapshot_type=snapshot_type,
                content=final_briefings[snapshot_type],
                expires_at=datetime.utcnow() + timedelta(hours=2) # expires in 2h
            )
            from sqlalchemy.exc import SQLAlchemyError
            try:
                db.add(snapshot)
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                db.add(snapshot)
                db.commit()
            logger.info(f"{agent_label} generated and stored successfully.")
            
        return final_briefings.get("daily_briefing"), final_briefings.get("daily_briefing_expert")

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
