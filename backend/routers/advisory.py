from fastapi import APIRouter, Depends, Query  # type: ignore[import-untyped]
from backend.core.advisory_engine import AdvisoryEngine  # type: ignore[import-untyped]
from backend.core.vector_store import get_vector_manager  # type: ignore[import-untyped]
from backend.dependencies import gemini_model  # type: ignore[import-untyped]
from backend.rate_limit import limiter  # type: ignore[import-untyped]
from fastapi import Request  # type: ignore[import-untyped]

from .auth import get_current_user
from backend import models, schemas, database
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/advisory", tags=["Advisory"])

# Init Core Engine with Gemini
advisory_engine = AdvisoryEngine(gemini_model=gemini_model)

@router.post("/symptom_check")
def check_symptoms(payload: dict, current_user: models.User = Depends(get_current_user)):
    """Analyzes symptoms using the Core Advisory Engine with user biodata."""
    symptoms = payload.get("symptoms", [])
    duration = payload.get("duration_days", 1)
    
    # Extract biodata for personalization
    user_metadata = {
        "genotype": current_user.genotype,
        "blood_group": current_user.blood_group,
        "health_conditions": current_user.health_conditions
    }
    
    result = advisory_engine.analyze_symptoms(symptoms, duration, user_metadata=user_metadata)
    return result

@router.post("/chat")
def chat_advisory(payload: schemas.ChatPayload, current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    """
    Stateful chat endpoint that uses universal fallbacks and high-performance reasoning models.
    """
    user_metadata = {
        "genotype": current_user.genotype,
        "blood_group": current_user.blood_group,
        "health_conditions": current_user.health_conditions
    }
    
    # Convert ChatMessage objects to dicts for the engine
    messages = [{"role": m.role, "content": m.content} for m in payload.messages]
    
    reply = advisory_engine.chat_with_ai(
        messages, 
        user_metadata=user_metadata, 
        enable_reasoning=payload.enable_reasoning,
        context=payload.context or ""
    )
    
    return {"reply": reply}

@router.post("/wellness_check")
def check_wellness(payload: dict, current_user: models.User = Depends(get_current_user)):
    """Analyzes vitals (BP) using the Core Advisory Engine."""
    sys = payload.get("systolic")
    dia = payload.get("diastolic")
    if sys is None or dia is None:
        return {"status": "Error", "advice": "Please provide both systolic and diastolic values."}
    result = advisory_engine.analyze_wellness(int(sys or 0), int(dia or 0))
    # We could also personalize BP advice here if needed, but the user specifically asked for symptoms/bio
    return result

@router.get("/search")
@limiter.limit("10/minute") # Rate limit added
def advisory_search(request: Request, query: str, k: int = Query(3)):
    """
    Hybrid RAG Search: Vector Store first, then Tavily.
    """
    vm = get_vector_manager()
    result = vm.hybrid_search(query, k=k)
    return result
