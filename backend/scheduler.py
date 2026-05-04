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
            skipped_count: int = 0
            for item in headlines:
                url: Optional[str] = item.get('url')
                item_title: str = str(item.get('title', ''))
                if not url:
                    # Fallback to headline text dedupe if no URL provided by scraper
                    exists = db.query(models.EBSAlert).filter(models.EBSAlert.text == item_title).first()
                else:
                    exists = db.query(models.EBSAlert).filter(models.EBSAlert.url == url).first()
                
                if exists:
                    skipped_count = skipped_count + 1  # type: ignore[operator]
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
            hl_list: List[Dict[str, Any]] = list(headlines)
            headlines = hl_list[:batch_limit]  # type: ignore[index]
        
        # Group reports for fusion (Now LOCAL and INSTANT via Batching)
        pending_reports = []
        if headlines:
            log_activity("IntelligenceEngine", f"Running AI batch extraction on {len(headlines)} articles...")
            batch_results = nlp_agent.extract_entities_batch(headlines)
            
            for item, (entities, nlp_trace) in zip(headlines, batch_results):
                if entities and entities.get('diseases') and entities.get('locations'):
                    for disease in entities['diseases']:
                        for location in entities['locations']:
                            pending_reports.append({
                                "source": item.get('source', 'Unknown'),
                                "url": item.get('url'),
                                "disease": disease,
                                "location": location,
                                "cases": 1, # Minimal observation
                                "text": item.get('title', item.get('text', '')),
                                "timestamp": item.get('timestamp')
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
                    db.flush() # Flush to get IDs
                    log_activity("AlertingEngine", f"Fused alert: {result['disease']} in {result['location']} (confidence={result['confidence_score']:.2f})")
                    
                    # --- Dispatch Email Notifications for High/Critical Alerts ---
                    if alert.risk_level in ["High", "Critical"]:
                        try:
                            from backend.core.email_utils import send_alert_notification
                            import threading
                            
                            # Find all users in the affected LGA or globally if not specified (Verification requirement bypassed)
                            query = db.query(models.User)
                            if result['location'] and result['location'].lower() != "lagos":
                                query = query.filter(models.User.location_lga.ilike(f"%{result['location']}%"))
                            
                            notified_users = query.all()
                            for user in notified_users:
                                action = f"Please remain vigilant regarding {result['disease']}. Follow NCDC protocols."
                                threading.Thread(
                                    target=send_alert_notification, 
                                    args=(user.email, user.username, result['disease'], result['location'], alert.risk_level, action)
                                ).start()
                                
                            if notified_users:
                                log_activity("NotificationEngine", f"Dispatched {len(notified_users)} email alerts for {result['disease']}.")
                        except Exception as e:
                            logger.error(f"Failed to dispatch email alerts: {e}")
                            
        else:
            # No dual-entity headlines — save disease-only articles as raw signals
            saved_raw = 0
            for item in headlines:
                item_dict = dict(item) if isinstance(item, dict) else {}
                item_title = str(item_dict.get('title', ''))
                entities, _ = nlp_agent.extract_entities(item_title)
                entities_dict: Dict[str, Any] = dict(entities) if isinstance(entities, dict) else {}
                
                diseases: List[str] = entities_dict.get('diseases', [])  # type: ignore[assignment]
                locations: List[str] = entities_dict.get('locations', [])  # type: ignore[assignment]
                # Save if at least a disease is found (location defaults to 'Lagos')
                if diseases:
                    alert = models.EBSAlert(
                        source=item_dict.get('source', 'NewsScout'),
                        url=item_dict.get('url'),
                        text=item_title,
                        timestamp=item_dict.get('timestamp') or datetime.now().replace(microsecond=0),
                        location_text=locations[0] if locations else 'Lagos',
                        disease=diseases[0],
                        collected_by="AutonomousAgent",
                        verified=False,
                        risk_level="Low"
                    )
                    db.add(alert)
                    saved_raw = saved_raw + 1  # type: ignore[operator]
            if saved_raw > 0:
                log_activity("AlertingEngine", f"Saved {saved_raw} new raw disease signals to EBS database.")
        
        db.commit()
        
        # 3. Vectorize verified alerts for RAG
        try:
            vm = get_vector_manager()
            new_docs = vm.ingest_ebs_alerts(db)
            if new_docs:
                log_activity("VectorEngine", f"Ingested {new_docs} text chunks into TitanVector.")
        except Exception as e:
            logger.error(f"Vector ingestion failed: {e}")
            
        log_activity("AutonomousAgent", "Monitoring cycle complete.")
        
        # --- Autonomous Phase 2 Cycles (with cooldowns to prevent rate limit bursts) ---
        try:
            orchestrator.run_predictive_cycle(db)
            log_activity("PredictiveAgent", "Forecast snapshots updated.")
            
            time.sleep(10)  # Cooldown between AI-heavy phases
            
            orchestrator.run_auto_verification_cycle(db)
            log_activity("VerifierAgent", "Auto-verification pass complete.")
            
            time.sleep(10)  # Cooldown between AI-heavy phases
            
            # Realtime Tavily intelligence (self-throttles to every 6h)
            orchestrator.run_realtime_intelligence_cycle(db)
            
            time.sleep(10)  # Cooldown between AI-heavy phases
            
            # Briefing run every 2 hours
            last_briefing = db.query(models.AutonomousSnapshot)\
                .filter(models.AutonomousSnapshot.snapshot_type == "daily_briefing")\
                .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
            
            if not last_briefing or (datetime.utcnow() - last_briefing.generated_at).total_seconds() > 7200:
                cit_brief, exp_brief = orchestrator.run_briefing_cycle(db)
                log_activity("BriefingAgent", "New 2-hour StAMP Briefing generated.")
                
                # Dispatch briefing emails to all users (Verification requirement bypassed)
                if cit_brief or exp_brief:
                    try:
                        from backend.core.email_utils import send_situational_briefing
                        import threading
                        all_users = db.query(models.User).all()
                        
                        for user in all_users:
                            is_expert = user.role.upper() in ["EXPERT", "ADMIN"]
                            content = exp_brief if is_expert and exp_brief else cit_brief
                            if content:
                                threading.Thread(
                                    target=send_situational_briefing,
                                    args=(user.email, user.username, content, is_expert)
                                ).start()
                                
                        if all_users:
                            log_activity("NotificationEngine", f"Dispatched {len(all_users)} situational briefing emails.")
                    except Exception as e:
                        logger.error(f"Failed to dispatch briefing emails: {e}")
        except Exception as e:
            logger.error(f"Error in Phase 2 Autonomous cycles: {e}")

    except Exception as e:
        error_str = str(e)
        if "UNIQUE constraint" in error_str or "duplicate key" in error_str:
            # Duplicate URL — expected when re-scraping same articles
            logger.warning(f"[System] Duplicate alert skipped (already in DB): {error_str[:80]}")
            db.rollback()
        else:
            log_activity("System", f"Error in monitoring job: {error_str}")
            db.rollback()
    finally:
        db.close()


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
