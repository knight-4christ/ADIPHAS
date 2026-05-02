from fastapi import APIRouter, Depends, HTTPException  # type: ignore[import-untyped]
from sqlalchemy.orm import Session  # type: ignore[import-untyped]
from datetime import datetime, timedelta
from typing import List, Optional

from backend import models, schemas  # type: ignore[import-untyped]
from backend.database import get_db  # type: ignore[import-untyped]
from backend.dependencies import gemini_model, log_activity  # type: ignore[import-untyped]
from backend.routers.auth import get_current_user, check_role  # type: ignore[import-untyped]

router = APIRouter(tags=["Reporting & Fusion"])

@router.post("/api/ebs/submit", response_model=schemas.EBSAlertResponse)
def submit_ebs(alert: schemas.EBSAlertCreate, db: Session = Depends(get_db)):
    db_alert = models.EBSAlert(
        source=alert.source,
        text=alert.text,
        timestamp=alert.timestamp,
        location_text=alert.location_text,
        location_lat=alert.location_lat,
        location_lon=alert.location_lon,
        disease=alert.disease,
        collected_by=alert.collected_by,
        summary=alert.summary,
        ai_powered=alert.ai_powered,
        policy_alert=alert.policy_alert,
        requires_hitl=alert.requires_hitl,
        verified=False  # Requires expert validation
    )
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert

@router.get("/api/ebs/list", response_model=List[schemas.EBSAlertResponse])
def list_alerts(limit: int = 200, db: Session = Depends(get_db)):
    """Returns alerts ordered by newest first. Defaults to latest 200 to prevent stale data overload."""
    return db.query(models.EBSAlert)\
        .order_by(models.EBSAlert.timestamp.desc())\
        .limit(limit)\
        .all()

@router.post("/api/ebs/{alert_id}/verify")
def verify_alert(alert_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(check_role("EXPERT"))):
    alert = db.query(models.EBSAlert).filter(models.EBSAlert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.verified = True
    db.commit()
    log_activity("ExpertManager", f"Alert {alert_id} verified by {current_user.username}")
    return {"status": "verified"}

@router.delete("/api/ebs/{alert_id}")
def discard_alert(alert_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(check_role("EXPERT"))):
    """Discards/removes an EBS Alert. Requires EXPERT role."""
    alert = db.query(models.EBSAlert).filter(models.EBSAlert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()
    log_activity("ExpertManager", f"Alert {alert_id} discarded by {current_user.username}")
    return {"status": "discarded"}

@router.get("/api/data/fusion_status")
def get_fusion_status(db: Session = Depends(get_db)):
    """Returns the latest Dempster-Shafer knowledge fusion report."""
    snapshot = db.query(models.AutonomousSnapshot)\
        .filter(models.AutonomousSnapshot.snapshot_type == "knowledge_fusion")\
        .order_by(models.AutonomousSnapshot.generated_at.desc()).first()
    
    if snapshot:
        import json
        # Parse content as JSON if possible, otherwise return as string
        content_data = snapshot.content
        try:
            content_data = json.loads(snapshot.content) if snapshot.content else None
        except (json.JSONDecodeError, TypeError):
            pass
        return {
            "generated_at": snapshot.generated_at,
            "content": content_data
        }
    return {"status": "No fusion available yet. Waiting for background agent."}

# --- Intelligence Briefing Endpoint (with Caching to prevent AI spam) ---
briefing_ai_cache = {}  # Format: {(lga, role): (insight, timestamp)}
CACHE_EXPIRY = timedelta(minutes=10)

@router.get("/api/intelligence/briefing")
def get_briefing(lga: Optional[str] = None, role: str = "CITIZEN", db: Session = Depends(get_db)):
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
            from backend.core.model_config import smart_generate  # type: ignore[import-untyped]
            text, model_used = smart_generate(gemini_model, prompt, context="IntelligenceBriefing")
            
            if text:
                ai_insight = text
                # Update Cache
                briefing_ai_cache[cache_key] = (ai_insight, now)
            else:
                ai_insight = "AI analysis temporarily unavailable across all models."
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
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
