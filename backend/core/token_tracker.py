"""
Token Tracker for AI API Usage (Gemini + OpenRouter).
Logs how many tokens are consumed per API call to help monitor quota.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# In-memory running totals for this server session
_session_totals = {
    "prompt_tokens": 0,
    "candidate_tokens": 0,
    "total_tokens": 0,
    "call_count": 0,
}

# Separate tracking for OpenRouter usage
_openrouter_totals = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "call_count": 0,
}

# Combined across all providers
_combined_totals = {
    "total_tokens": 0,
    "total_calls": 0,
}


def track_usage(response, context: str = ""):
    """
    Extract and log token usage from a Gemini API response.
    Call this after every `models.generate_content(...)` call.
    
    Args:
        response: The response object from google.genai
        context: A short human-readable label (e.g. "StartupInsight", "SymptomCheck")
    """
    try:
        meta = getattr(response, "usage_metadata", None)
        if meta:
            prompt_tokens = getattr(meta, "prompt_token_count", 0) or 0
            candidate_tokens = getattr(meta, "candidates_token_count", 0) or 0
            total = prompt_tokens + candidate_tokens

            _session_totals["prompt_tokens"] += prompt_tokens
            _session_totals["candidate_tokens"] += candidate_tokens
            _session_totals["total_tokens"] += total
            _session_totals["call_count"] += 1
            
            _combined_totals["total_tokens"] += total
            _combined_totals["total_calls"] += 1

            logger.info(
                f"[TokenTracker] {context} | "
                f"Prompt: {prompt_tokens}, Response: {candidate_tokens}, "
                f"Call Total: {total} | "
                f"Session Running Total: {_combined_totals['total_tokens']} tokens "
                f"({_combined_totals['total_calls']} calls)"
            )
        else:
            logger.warning(f"[TokenTracker] {context} | No usage_metadata found on response.")
    except Exception as e:
        logger.error(f"[TokenTracker] Failed to extract usage: {e}")


def track_openrouter_usage(model_id: str, prompt_tokens: int = 0, completion_tokens: int = 0, context: str = ""):
    """
    Track token usage from an OpenRouter API response.
    
    Args:
        model_id: The OpenRouter model identifier
        prompt_tokens: Number of prompt tokens from the response usage field
        completion_tokens: Number of completion tokens from the response usage field
        context: A short human-readable label
    """
    total = prompt_tokens + completion_tokens
    
    _openrouter_totals["prompt_tokens"] += prompt_tokens
    _openrouter_totals["completion_tokens"] += completion_tokens
    _openrouter_totals["total_tokens"] += total
    _openrouter_totals["call_count"] += 1
    
    _combined_totals["total_tokens"] += total
    _combined_totals["total_calls"] += 1
    
    logger.info(
        f"[TokenTracker] {context} [model={model_id}] | "
        f"Prompt: {prompt_tokens}, Response: {completion_tokens}, "
        f"Call Total: {total} | "
        f"Session Running Total: {_combined_totals['total_tokens']} tokens "
        f"({_combined_totals['total_calls']} calls)"
    )


def get_session_totals() -> dict:
    """Returns the running token totals for the current server session — all providers."""
    return {
        "gemini": {**_session_totals},
        "openrouter": {**_openrouter_totals},
        "combined": {**_combined_totals},
        "snapshot_time": datetime.now().replace(microsecond=0).isoformat()
    }
