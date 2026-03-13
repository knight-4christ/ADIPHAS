from fastapi import APIRouter, Depends, HTTPException  # type: ignore[import-untyped]
from sqlalchemy.orm import Session  # type: ignore[import-untyped]
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import time

from backend import models, schemas  # type: ignore[import-untyped]
from backend.database import get_db  # type: ignore[import-untyped]
from backend.dependencies import log_activity, news_agent, fusion_agent, nlp_agent  # type: ignore[import-untyped]
import json

router = APIRouter(tags=["System & Monitoring"])

@router.get("/api/system/activity")
def get_system_activity(limit: int = 50, db: Session = Depends(get_db)):
    """Returns recent system activities from the db for the live log."""
    activities = db.query(models.SystemActivity).order_by(models.SystemActivity.timestamp.desc()).limit(limit).all()
    # Return in chronological order for the UI
    return [{"timestamp": str(a.timestamp), "agent": a.agent, "message": a.message} for a in reversed(activities)]

@router.get("/api/system/activity/history")
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

@router.get("/api/acquisition/news/scrape")
def scrape_news():
    """
    Triggers the NewsScraperAgent to fetch health headlines.
    """
    try:
        headlines, trace = news_agent.scrape()
        return {"status": "success", "count": len(headlines), "data": headlines, "trace": trace}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/intelligence/fuse")
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

@router.get("/api/intelligence/sources")
def get_intelligence_sources():
    """Returns the list of monitored epidemiological sources and their reliability weights."""
    return fusion_agent.get_source_registry()

@router.get("/api/system/forecasts")
def get_autonomous_forecasts(db: Session = Depends(get_db)):
    """Returns all pre-calculated forecasts and anomalies."""
    snapshots = db.query(models.PredictiveSnapshot).all()
    return snapshots

@router.get("/api/system/realtime-intel")
def get_realtime_intelligence(db: Session = Depends(get_db)):
    """Returns the latest Tavily-powered real-time disease intelligence snapshot."""
    snapshot = db.query(models.AutonomousSnapshot)\
        .filter(models.AutonomousSnapshot.snapshot_type == "realtime_intelligence")\
        .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
    return snapshot

# Globals for primitive endpoint caching (so we don't spam SQLite during Dashboard polling)
_cached_system_metrics = None
_cached_system_metrics_time = 0

@router.get("/api/system/metrics")
def get_system_metrics(db: Session = Depends(get_db)):
    """Returns today's scraping and intelligence metrics. Cached for 5s TTL."""
    global _cached_system_metrics
    global _cached_system_metrics_time
    
    current_time = time.time()
    if _cached_system_metrics and (current_time - _cached_system_metrics_time) < 5.0:
        return _cached_system_metrics

    from sqlalchemy import func, cast, Date  # type: ignore[import-untyped]
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
    
    # User requested cumulative daily totals, not just the last run's count.
    total_scraped_today = 0
    all_scrape_sources = set()
    
    for sa in scout_activities:
        m = re.search(r'Scraped (\d+) articles?\. Sources: (.+)', sa.message)
        if m:
            total_scraped_today += int(m.group(1))
            sources_chunk = m.group(2)
            if sources_chunk != "None":
                for src in list(map(str.strip, sources_chunk.split(','))):  # type: ignore[arg-type]
                    all_scrape_sources.add(src)
    
    # Articles processed/skipped from IntelligenceEngine
    intel_activities = db.query(models.SystemActivity).filter(
        models.SystemActivity.agent == "IntelligenceEngine",
        cast(models.SystemActivity.timestamp, Date) == today
    ).order_by(models.SystemActivity.timestamp.desc()).all()
    
    total_articles_skipped = 0
    total_articles_batched = 0
    
    for sa in intel_activities:
        m_skip = re.search(r'Skipped (\d+)', sa.message)
        if m_skip:
            total_articles_skipped += int(m_skip.group(1))
        
        m_batch1 = re.search(r'Processing top (\d+) out of (\d+)', sa.message)
        if m_batch1:
            total_articles_batched += int(m_batch1.group(1)) # Count the limited batch
            continue # Prioritize this over the next regex if both exist
            
        m_batch2 = re.search(r'Running AI batch extraction on (\d+)', sa.message)
        if m_batch2:
            total_articles_batched += int(m_batch2.group(1))
    
    # Alerts saved today
    alerts_saved_msg = [sa for sa in db.query(models.SystemActivity).filter(
        models.SystemActivity.agent == "AlertingEngine",
        cast(models.SystemActivity.timestamp, Date) == today
    ).all()]
    alerts_saved_today = len(alerts_saved_msg)
    
    # Format sources beautifully
    last_scrape_sources = ", ".join(sorted(list(all_scrape_sources))) if all_scrape_sources else "None yet"
    
    # NEW CACHING IMPLEMENTATION:
    # Save the computed result before returning
    computed_metrics = {
        "today_activity_by_agent": metrics,
        "total_alerts_in_db": total_alerts,
        "verified_alerts": verified_alerts,
        "last_scrape_articles": total_scraped_today,
        "last_scrape_sources": last_scrape_sources,
        "articles_skipped": total_articles_skipped,
        "articles_new": total_articles_batched,
        "alerts_saved_today": alerts_saved_today,
        "last_updated": datetime.now().replace(microsecond=0).isoformat()
    }
    
    _cached_system_metrics = computed_metrics
    _cached_system_metrics_time = current_time
    
    return computed_metrics

# --- NLP Extraction Endpoint (for UI evaluation module) ---

@router.post("/api/nlp/extract")
def nlp_extract(payload: dict):
    """Extracts disease/location entities from raw text using the NLP Agent."""
    text = payload.get("text", "")
    entities, trace = nlp_agent.extract_entities(text)
    return {"entities": entities, "trace": trace}


# --- Evaluation Endpoints ---

@router.get("/api/evaluation/metrics")
def get_evaluation_metrics(db: Session = Depends(get_db)):
    """Returns aggregate NLP performance metrics from evaluation samples."""
    samples = db.query(models.EvaluationSample).all()
    f1_scores = [s.f1_score for s in samples if s.f1_score is not None]
    avg_f1 = round(float(sum(f1_scores)) / len(f1_scores), 4) if f1_scores else 0.0  # type: ignore[call-overload]
    return {"total_samples": len(samples), "avg_f1": avg_f1}

@router.get("/api/evaluation/samples")
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

@router.post("/api/evaluation/submit")
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
        return round(float(2 * precision * recall / (precision + recall)), 4) if (precision + recall) > 0 else 0.0  # type: ignore[call-overload]

    disease_f1 = compute_f1(expected.get("diseases", []), actual.get("diseases", []))
    location_f1 = compute_f1(expected.get("locations", []), actual.get("locations", []))
    avg_f1 = round(float(disease_f1 + location_f1) / 2, 4)  # type: ignore[call-overload]

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

