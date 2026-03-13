from fastapi import APIRouter, Depends, Query  # type: ignore[import-untyped]
from backend.core.advisory_engine import AdvisoryEngine  # type: ignore[import-untyped]
from backend.core.vector_store import get_vector_manager  # type: ignore[import-untyped]
from backend.dependencies import gemini_model  # type: ignore[import-untyped]
from backend.rate_limit import limiter  # type: ignore[import-untyped]
from fastapi import Request  # type: ignore[import-untyped]

router = APIRouter(prefix="/api/advisory", tags=["Advisory"])

# Init Core Engine with Gemini
advisory_engine = AdvisoryEngine(gemini_model=gemini_model)

@router.post("/symptom_check")
def check_symptoms(payload: dict):
    """Analyzes symptoms using the Core Advisory Engine."""
    symptoms = payload.get("symptoms", [])
    duration = payload.get("duration_days", 1)
    result = advisory_engine.analyze_symptoms(symptoms, duration)
    return result

@router.post("/wellness_check")
def check_wellness(payload: dict):
    """Analyzes vitals (BP) using the Core Advisory Engine."""
    sys = payload.get("systolic")
    dia = payload.get("diastolic")
    if sys is None or dia is None:
        return {"status": "Error", "advice": "Please provide both systolic and diastolic values."}
    result = advisory_engine.analyze_wellness(int(sys or 0), int(dia or 0))
    return result

@router.get("/search")
@limiter.limit("10/minute") # Rate limit added
def advisory_search(request: Request, query: str, k: int = Query(3)):
    """
    Hybrid RAG Search: ChromaDB first, then Tavily.
    """
    vm = get_vector_manager()
    result = vm.hybrid_search(query, k=k)
    return result
