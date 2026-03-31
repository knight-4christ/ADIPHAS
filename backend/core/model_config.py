import logging
import os
import requests
import json
from datetime import datetime

logger = logging.getLogger(__name__)

# Model fallback chain — ordered by preference for NATIVE Gemini
MODEL_CHAIN = [
    "gemini-2.0-flash",
    "gemini-2.5-flash",
]

class ModelState:
    def __init__(self):
        self.current_index: int = 0
        self.last_switch: str | None = None
        self.switch_count: int = 0

_state = ModelState()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# OpenRouter Free Model Chain (Verified active as of 2026-03-31)
# Includes reasoning-capable models for advanced analysis
OPENROUTER_CHAIN = [
    "xiaomi/mimo-v2-pro",
    "stepfun/step-3.5-flash:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "google/gemma-3-27b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "minimax/minimax-m2.5:free",
]

def get_current_model() -> str:
    """Returns the currently active model name."""
    return MODEL_CHAIN[_state.current_index]


def switch_to_next_model() -> str:
    """Moves to the next model in the fallback chain. Returns the new model name."""
    old_model = get_current_model()
    _state.current_index = (_state.current_index + 1) % len(MODEL_CHAIN)
    _state.last_switch = datetime.now().replace(microsecond=0).isoformat()
    _state.switch_count += 1
    new_model = get_current_model()
    logger.warning(f"[ModelFallback] Switched from {old_model} -> {new_model} (switch #{_state.switch_count})")
    return new_model

def _generate_via_openrouter(prompt: str, context: str = "", enable_reasoning: bool = False) -> tuple[str | None, str | None]:
    """Ultimate fallback via OpenRouter REST API with its own internal retry chain. Returns (text, model_id)."""
    if not OPENROUTER_API_KEY:
        logger.error("[OpenRouter] API Key missing. Fallback impossible.")
        return None, None

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://adiphas.ai",
        "X-Title": "ADIPHAS Intelligence",
    }
    
    for model_id in OPENROUTER_CHAIN:
        logger.info(f"[OpenRouter] Attempting {context} using {model_id} (Reasoning: {enable_reasoning})")
        
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        # Only enable reasoning for models that support it or if explicitly requested
        if enable_reasoning or "hunter" in model_id or "thinking" in model_id:
            payload["reasoning"] = {"enabled": True}
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
            if response.status_code != 200:
                logger.warning(f"[OpenRouter] {model_id} failed with status {response.status_code}: {response.text}")
                continue
                
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                message = result['choices'][0]['message']
                text = message.get('content') or ""
                
                # Log reasoning for transparency, but NEVER include in output
                # Reasoning can be a string or a list of objects — either way, strip it
                if 'reasoning_details' in message and message['reasoning_details']:
                    logger.debug(f"[OpenRouter] Reasoning trace received from {model_id} (stripped from output)")
                
                logger.info(f"[OpenRouter] SUCCESS with {model_id} for {context}")
                return text.strip(), model_id
            else:
                logger.warning(f"[OpenRouter] {model_id} returned empty choices: {result}")
                
        except Exception as e:
            logger.error(f"[OpenRouter] {model_id} error for {context}: {e}")
            continue
            
    return None, None


def _embed_via_openrouter(text_or_list: str | list[str]) -> list[list[float]] | None:
    """Fallback embedding generation via OpenRouter."""
    if not OPENROUTER_API_KEY:
        return None

    model = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    url = "https://openrouter.ai/api/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
        "Content-Type": "application/json",
    }
    
    inputs = [text_or_list] if isinstance(text_or_list, str) else text_or_list
    
    # OpenRouter embedding payload structure
    payload = {
        "model": model,
        "input": inputs
    }
    
    try:
        logger.info(f"[OpenRouterEmbed] Attempting fallback using {model}")
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract embeddings
        embeddings = [item["embedding"] for item in data["data"]]
        return embeddings
    except Exception as e:
        logger.error(f"[OpenRouterEmbed] Fallback failed: {e}")
        return None


def get_model_status_log() -> str:
    """Returns a formatted summary of the active AI model chain and fallbacks for startup logging."""
    native_chain = " -> ".join(MODEL_CHAIN)
    or_chain = " -> ".join(OPENROUTER_CHAIN)
    
    status = [
        "\n" + "="*50,
        "ADIPHAS INTELLIGENCE: AI MODEL STATUS",
        "="*50,
        f"Primary Native Chain: {native_chain}",
        f"Verified Fallback (OR): {or_chain}",
        f"Active Model index: {_state.current_index} ({get_current_model()})",
        f"OpenRouter Fallback: {'ENABLED' if OPENROUTER_API_KEY else 'DISABLED (Check .env)'}",
        f"Total Fallback Switches: {_state.switch_count}",
        "="*50 + "\n"
    ]
    return "\n".join(status)


def smart_generate(gemini_client, prompt: str, context: str = "", enable_reasoning: bool = False):
    """
    Calls Gemini with automatic model fallback on 429 errors.
    If all native models fail, tries OpenRouter.
    """
    from backend.core.token_tracker import track_usage
    
    attempts = len(MODEL_CHAIN)
    for _ in range(attempts):
        model = get_current_model()
        try:
            # Native Gemini Flash supports some reasoning-like behaviors by default
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
            # Universal error catching for fallback
            if any(code in error_str for code in ["429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND", "503"]):
                logger.warning(f"[Gemini] {model} unavailable ({error_str[:50]}) for {context}. Switching model...")
                switch_to_next_model()
            else:
                logger.error(f"[Gemini] {model} critical error for {context}: {e}")
                # Try OpenRouter even on non-quota errors if it's the last hope
                break
    
    # Ultimate Fallback: OpenRouter (ENGAGED ONLY IF NATIVE EXHAUSTED)
    if OPENROUTER_API_KEY:
        logger.warning(f"[Gemini] All native models exhausted for {context}. Engaging OpenRouter Fallback Tier...")
        fallback_text, or_model = _generate_via_openrouter(prompt, context=context, enable_reasoning=enable_reasoning)
        if fallback_text:
            return fallback_text, f"openrouter/{or_model}"
    else:
        logger.error(f"[Gemini] No OpenRouter API Key available for emergency fallback.")
        
    logger.error(f"[Gemini] EVERY intelligence path exhausted for {context}.")
    return None, None


def get_model_status() -> dict:
    """Returns the current model fallback status."""
    return {
        "current_model": get_current_model(),
        "model_chain": MODEL_CHAIN,
        "openrouter_chain": OPENROUTER_CHAIN,
        "switch_count": _state.switch_count,
        "last_switch": _state.last_switch,
        "openrouter_enabled": bool(OPENROUTER_API_KEY)
    }
