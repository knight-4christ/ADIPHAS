import logging
import threading
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from backend import models, database
from backend.dependencies import (
    log_activity, news_agent, nlp_agent, fusion_agent, orchestrator, gemini_model
)
from backend.core.vector_store import get_vector_manager

logger = logging.getLogger(__name__)

# Global startup insight cache (accessed by routers)
startup_insight_cache = {"insight": None, "generated_at": None}

def autonomous_monitoring_job():
    """
    Background job that runs every 15 minutes to scrape news and extract alerts.
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
        
        # --- NEW: Autonomous Phase 2 Cycles ---
        try:
            orchestrator.run_predictive_cycle(db)
            log_activity("PredictiveAgent", "Forecast snapshots updated.")
            
            orchestrator.run_auto_verification_cycle(db)
            log_activity("VerifierAgent", "Auto-verification pass complete.")
            
            # Realtime Tavily intelligence (self-throttles to every 6h)
            orchestrator.run_realtime_intelligence_cycle(db)
            
            # Briefing run once per day (checks for existing within 24h)
            last_briefing = db.query(models.AutonomousSnapshot)\
                .filter(models.AutonomousSnapshot.snapshot_type == "daily_briefing")\
                .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
            
            if not last_briefing or (datetime.utcnow() - last_briefing.generated_at).total_seconds() > 86400:
                orchestrator.run_briefing_cycle(db)
                log_activity("BriefingAgent", "New Daily Briefing generated.")
                
        except Exception as e:
            logger.error(f"Error in Phase 2 Autonomous cycles: {e}")

    except Exception as e:
        log_activity("System", f"Error in monitoring job: {str(e)}")
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
                    rag_context = "\n".join([f"- {r.get('content', '')}" for r in rag_response["results"] if isinstance(r, dict)][:3])

                alert_summary = "\n".join([f"- {a.disease} in {a.location_text} ({a.risk_level})" for a in recent_alerts[:5]])
                
                prompt = f"""3-sentence startup briefing. Alerts:\n{alert_summary}\nContext:\n{rag_context}\nPatterns? Concerns? Monitor?"""
                from backend.core.model_config import smart_generate
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


def start_scheduler():
    """Initializes and starts the background scheduler and deferred startup tasks."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(autonomous_monitoring_job, 'interval', minutes=15)
    scheduler.start()
    logger.info("Background Scheduler started.")
    
    # Self-healing database sweep
    db = database.SessionLocal()
    try:
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
        
    threading.Thread(target=_generate_startup_insight, daemon=True).start()
    threading.Thread(target=autonomous_monitoring_job, daemon=True).start()
