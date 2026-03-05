"""
Centralized Gemini Model Configuration with Automatic Fallback.
If one model's quota is exhausted (429), the system switches to the next model in the chain.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Model fallback chain — ordered by preference
# The system tries each model in order. If a 429 is hit, it moves to the next.
MODEL_CHAIN = [
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-1.5-flash",
]

# Track which model is currently active
_state = {
    "current_index": 0,
    "last_switch": None,
    "switch_count": 0,
}


def get_current_model() -> str:
    """Returns the currently active model name."""
    return MODEL_CHAIN[_state["current_index"]]


def switch_to_next_model() -> str:
    """Moves to the next model in the fallback chain. Returns the new model name."""
    old_model = get_current_model()
    _state["current_index"] = (_state["current_index"] + 1) % len(MODEL_CHAIN)
    _state["last_switch"] = datetime.now().replace(microsecond=0).isoformat()
    _state["switch_count"] += 1
    new_model = get_current_model()
    logger.warning(f"[ModelFallback] Switched from {old_model} → {new_model} (switch #{_state['switch_count']})")
    return new_model


def smart_generate(gemini_client, prompt: str, context: str = ""):
    """
    Calls Gemini with automatic model fallback on 429 errors.
    Tries each model in the chain before giving up.
    
    Args:
        gemini_client: The google.genai Client instance
        prompt: The prompt text
        context: Human-readable label for token tracking
    
    Returns:
        (response_text, model_used) tuple, or (None, None) if all models fail
    """
    from backend.core.token_tracker import track_usage
    
    attempts = len(MODEL_CHAIN)
    for _ in range(attempts):
        model = get_current_model()
        try:
            response = gemini_client.models.generate_content(
                model=model,
                contents=prompt
            )
            # Track tokens with model name
            track_usage(response, context=f"{context} [model={model}]")
            logger.info(f"[Gemini] {context} completed using {model}")
            return response.text.strip(), model
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                logger.warning(f"[Gemini] {model} quota exhausted for {context}. Switching model...")
                switch_to_next_model()
            else:
                logger.error(f"[Gemini] {model} failed for {context}: {e}")
                return None, model
    
    logger.error(f"[Gemini] All models exhausted for {context}. No fallback available.")
    return None, None


def get_model_status() -> dict:
    """Returns the current model fallback status."""
    return {
        "current_model": get_current_model(),
        "model_chain": MODEL_CHAIN,
        "switch_count": _state["switch_count"],
        "last_switch": _state["last_switch"],
    }
