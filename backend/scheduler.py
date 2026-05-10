import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]
from sqlalchemy import text  # type: ignore[import-untyped]
import asyncio

from backend import models, database  # type: ignore[import-untyped]
from backend.dependencies import (  # type: ignore[import-untyped]
    log_activity, news_agent, nlp_agent, fusion_agent, orchestrator, gemini_model
)
from backend.core.vector_store import get_vector_manager  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Global startup insight cache (accessed by routers)
startup_insight_cache: Dict[str, Any] = {"insight": None, "generated_at": None}

def autonomous_monitoring_job():
    """
    Background job that runs every 2 hours to scrape news and extract alerts.
    """
    logger.info(f"[{datetime.now().replace(microsecond=0)}] Autonomous Agent waking up to scan for outbreaks...")
    
    # 1. Acquire News Intelligence (Scraping phase - No DB session yet)
    headlines = []
    try:
        logger.info("Starting Autonomous Monitoring Cycle...")
        # Note: log_activity internally opens/closes its own session, so it's safe.
        log_activity("AutonomousAgent", "Waking up to scan for outbreaks...")
        
        headlines, scrape_trace = news_agent.scrape()
        sources_hit = set(h.get('source') for h in headlines if h.get('source'))
        sources_str = ", ".join(sources_hit) if sources_hit else "None"
        log_activity("SCOUT", f"Scraped {len(headlines)} articles. Sources: {sources_str}")
        
        for st in scrape_trace:
            if st.get('level') == 'info':
                log_activity("SCOUT", st.get('step'))
                
    except Exception as e:
        log_activity("SCOUT", f"Scraping failed: {e}")
        headlines = []

    # 1.2 Deduplication (Short DB burst)
    filtered_headlines = []
    skipped_count = 0
    db_dedupe = database.SessionLocal()
    seen_urls = set()
    try:
        for item in headlines:
            url: Optional[str] = item.get('url')
            item_title: str = str(item.get('title', ''))
            
            if url and url in seen_urls:
                skipped_count += 1
                continue
                
            if not url:
                exists = db_dedupe.query(models.EBSAlert).filter(models.EBSAlert.text == item_title).first()
            else:
                exists = db_dedupe.query(models.EBSAlert).filter(models.EBSAlert.url == url).first()
            
            if exists:
                skipped_count += 1
            else:
                filtered_headlines.append(item)
                if url:
                    seen_urls.add(url)
        
        if skipped_count > 0:
            log_activity("IntelligenceEngine", f"Skipped {skipped_count} previously processed articles.")
        db_dedupe.commit()
    except Exception as e:
        logger.error(f"Deduplication failed: {e}")
        db_dedupe.rollback()
    finally:
        db_dedupe.close()

    # 1.5 Batching & AI Extraction (Long AI phase - DB IS CLOSED)
    chunk_size = 15
    hl_list = filtered_headlines
    total_new = len(hl_list)
    pending_reports = []
    
    if total_new > 0:
        log_activity("IntelligenceEngine", f"Processing {total_new} new articles in chunks of {chunk_size}...")
        for i in range(0, total_new, chunk_size):
            chunk = hl_list[i : i + chunk_size]
            log_activity("IntelligenceEngine", f"Running AI batch extraction on chunk {i//chunk_size + 1} ({len(chunk)} articles)...")
            try:
                batch_results = nlp_agent.extract_entities_batch(chunk)
                for item, (entities, nlp_trace) in zip(chunk, batch_results):
                    if entities and entities.get('diseases') and entities.get('locations'):
                        for disease in entities['diseases']:
                            for location in entities['locations']:
                                pending_reports.append({
                                    "source": item.get('source', 'Unknown'),
                                    "url": item.get('url'),
                                    "disease": disease,
                                    "location": location,
                                    "cases": 1,
                                    "text": item.get('title', item.get('text', '')),
                                    "timestamp": item.get('timestamp')
                                })
            except Exception as e:
                logger.error(f"Chunk processing failed: {e}")
                continue

    # 2. Saving Fused Alerts (DB session burst)
    db_save = database.SessionLocal()
    saved_urls = set()
    try:
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
                    import uuid
                    alert_url = result.get('url')
                    if alert_url:
                        # Check DB for existing URL to prevent UniqueViolation
                        existing = db_save.query(models.EBSAlert).filter(models.EBSAlert.url == alert_url).first()
                        if existing or alert_url in saved_urls:
                            alert_url = f"{alert_url}#{result['disease'].replace(' ', '')}-{result['location'].replace(' ', '')}-{uuid.uuid4().hex[:8]}"
                        
                    alert = models.EBSAlert(
                        source="Fused Intelligence",
                        url=alert_url,
                        text=f"Confirmed {result['disease']} activity in {result['location']}",
                        timestamp=datetime.now().replace(microsecond=0),
                        location_text=result['location'],
                        disease=result.get('disease'),
                        collected_by="AutonomousAgent",
                        verified=False,
                        risk_level="High" if result.get('severity_score', 0) > 0.7 or result['confidence_score'] > 0.8 else ("Medium" if result['confidence_score'] > 0.5 else "Low")
                    )
                    db_save.add(alert)
                    db_save.flush()
                    if alert_url:
                        saved_urls.add(alert_url)
                    log_activity("AlertingEngine", f"Fused alert: {result['disease']} in {result['location']} (confidence={result['confidence_score']:.2f})")
                    
                    if alert.risk_level in ["High", "Critical"]:
                        try:
                            from backend.core.email_utils import send_alert_notification
                            import threading
                            notified_users = db_save.query(models.User)
                            if result['location'] and result['location'].lower() != "lagos":
                                notified_users = notified_users.filter(models.User.location_lga.ilike(f"%{result['location']}%"))
                            
                            users_list = notified_users.all()
                            for user in users_list:
                                threading.Thread(
                                    target=send_alert_notification, 
                                    args=(user.email, user.username, result['disease'], result['location'], alert.risk_level, "Stay vigilant.")
                                ).start()
                            if users_list:
                                log_activity("NotificationEngine", f"Dispatched {len(users_list)} email alerts.")
                        except Exception: pass
        else:
            # Raw disease signals
            saved_raw = 0
            for item in hl_list:
                entities, _ = nlp_agent.extract_entities(str(item.get('title', '')))
                diseases = entities.get('diseases', [])
                if diseases:
                    alert = models.EBSAlert(
                        source=item.get('source', 'NewsScout'),
                        url=item.get('url'),
                        text=str(item.get('title', '')),
                        timestamp=item.get('timestamp') or datetime.now().replace(microsecond=0),
                        location_text=entities.get('locations', ['Lagos'])[0],
                        disease=diseases[0],
                        collected_by="AutonomousAgent",
                        verified=False,
                        risk_level="Low"
                    )
                    db_save.add(alert)
                    saved_raw += 1
            if saved_raw > 0:
                log_activity("AlertingEngine", f"Saved {saved_raw} new raw disease signals.")

        # 3. Vector Ingestion
        try:
            vm = get_vector_manager()
            new_docs = vm.ingest_ebs_alerts(db_save)
            if new_docs:
                log_activity("VectorEngine", f"Ingested {new_docs} text chunks.")
        except Exception: pass

        db_save.commit()
        log_activity("AutonomousAgent", "Monitoring cycle complete.")

    except Exception as e:
        logger.error(f"Error in monitoring save phase: {e}")
        db_save.rollback()
    finally:
        db_save.close()

    # 4. Phase 2 (Predictive, Briefing, etc. - Isolated sessions)
    db_p2 = database.SessionLocal()
    try:
        orchestrator.run_predictive_cycle(db_p2)
        time.sleep(5)
        orchestrator.run_auto_verification_cycle(db_p2)
        time.sleep(5)
        orchestrator.run_realtime_intelligence_cycle(db_p2)
        time.sleep(5)
        
        # StAMP Briefing
        last_briefing = db_p2.query(models.AutonomousSnapshot)\
            .filter(models.AutonomousSnapshot.snapshot_type == "daily_briefing")\
            .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
        
        if not last_briefing or (datetime.utcnow() - last_briefing.generated_at).total_seconds() > 7200:
            cit_brief, exp_brief = orchestrator.run_briefing_cycle(db_p2)
            if cit_brief or exp_brief:
                # Dispatch Briefings (Threading handles its own logic)
                verified_users = db_p2.query(models.User).filter(models.User.is_email_verified == True).all()
                from backend.core.email_utils import send_situational_briefing
                import threading
                for user in verified_users:
                    is_expert = user.role.upper() in ["EXPERT", "ADMIN"]
                    content = exp_brief if is_expert and exp_brief else cit_brief
                    if content:
                        threading.Thread(target=send_situational_briefing, args=(user.email, user.username, content, is_expert)).start()

        db_p2.commit()
    except Exception as e:
        logger.error(f"Error in Autonomous Phase 2: {e}")
        db_p2.rollback()
    finally:
        db_p2.close()


def _generate_startup_insight():
    """Deferred startup insight: waits 30s for rate limits to clear, then retries."""
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
                vm = get_vector_manager()
                
                rag_query = "disease outbreaks health alerts Lagos"
                rag_response = vm.hybrid_search(rag_query, k=3, force_combine=True)
                rag_context = ""
                
                if rag_response and "results" in rag_response:
                    results_list = list(rag_response.get("results", []))
                    rag_context = "\n".join([f"- {r.get('content', '')}" for r in results_list[:3] if isinstance(r, dict)])  # type: ignore[index, misc]

                recent_list = list(recent_alerts)
                alert_summary = "\n".join([f"- {a.disease} in {a.location_text} ({a.risk_level})" for a in recent_list[:5]])  # type: ignore[index, misc]
                
                prompt = f"""3-sentence startup briefing. Alerts:\n{alert_summary}\nContext:\n{rag_context}\nPatterns? Concerns? Monitor?"""
                from backend.core.model_config import smart_generate  # type: ignore[import-untyped]
                text, model_used = smart_generate(gemini_model, prompt, context="StartupInsight")
                
                if text:
                    startup_insight_cache["insight"] = text
                    startup_insight_cache["generated_at"] = datetime.now().replace(microsecond=0).isoformat()
                    logger.info(f"[StartupInsight] Generated successfully using {model_used} with Hybrid RAG.")
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


async def start_scheduler():
    """Initializes and starts the background scheduler and deferred startup tasks."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(autonomous_monitoring_job, 'interval', minutes=120)
    scheduler.start()
    logger.info("Background Scheduler started.")
    
    # Self-healing database sweep (SQLite-specific fixes)
    from backend.database import is_sqlite
    db = database.SessionLocal()
    try:
        if is_sqlite:
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
        
    # Schedule the initial runs on the background scheduler's thread pool
    # We stagger them to avoid concurrent lock contention on the vector store at cold-start
    import threading
    
    # Validate model pool availability in background
    from backend.core.model_config import validate_model_pool
    threading.Thread(target=validate_model_pool, daemon=True, name="ModelValidation").start()
    
    threading.Thread(target=_generate_startup_insight, daemon=True, name="StartupInsight").start()
    
    # Periodic briefing watchdog — ensures StAMP briefing always exists
    def _briefing_watchdog():
        """Checks every 15 minutes if a valid briefing exists. If not, triggers generation."""
        time.sleep(120)  # Initial delay: wait for first monitoring cycle
        while True:
            try:
                db_check = database.SessionLocal()
                last_briefing = db_check.query(models.AutonomousSnapshot)\
                    .filter(models.AutonomousSnapshot.snapshot_type == "daily_briefing")\
                    .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
                
                needs_briefing = False
                if not last_briefing:
                    needs_briefing = True
                    logger.info("[BriefingWatchdog] No briefing found in DB. Triggering generation...")
                elif (datetime.utcnow() - last_briefing.generated_at).total_seconds() > 86400:
                    needs_briefing = True
                    logger.info("[BriefingWatchdog] Briefing expired (>24h). Triggering regeneration...")
                
                if needs_briefing:
                    orchestrator.run_briefing_cycle(db_check, force=True)
                    log_activity("BriefingWatchdog", "Forced briefing generation (watchdog).")
                
                db_check.close()
            except Exception as e:
                logger.warning(f"[BriefingWatchdog] Check failed: {e}")
            
            time.sleep(900)  # Check every 15 minutes
    
    threading.Thread(target=_briefing_watchdog, daemon=True, name="BriefingWatchdog").start()
    
    def delayed_monitoring():
        logger.info("[Scheduler] Monitoring cycle deferred for 60s to allow StartupInsight to clear...")
        time.sleep(60) # Wait for StartupInsight to clear initial RAG check
        
        # Periodic liveness trace
        def liveness_heartbeat():
            while True:
                logger.info(f"[Liveness] Scheduler threads active at {datetime.now().replace(microsecond=0)}")
                time.sleep(300) # Every 5 mins
        
        threading.Thread(target=liveness_heartbeat, daemon=True, name="LivenessMonitor").start()
        
        autonomous_monitoring_job()
        
    threading.Thread(target=delayed_monitoring, daemon=True, name="MonitoringCycle").start()
