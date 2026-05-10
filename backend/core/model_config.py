import logging
import os
import requests
import json
import time
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED MODEL POOL — 20 models across Gemini Native + OpenRouter Free Tier
# ══════════════════════════════════════════════════════════════════════════════
UNIFIED_MODEL_POOL = [
    # --- Gemini Native (2 models) — highest reliability, no OpenRouter overhead ---
    {"id": "gemini-2.0-flash",                              "provider": "gemini",     "tier": 1},
    {"id": "gemini-2.5-flash",                              "provider": "gemini",     "tier": 1},
    
    # --- OpenRouter Tier 1: Large/Premium ---
    {"id": "nousresearch/hermes-3-llama-3.1-405b:free",     "provider": "openrouter", "tier": 1},
    {"id": "nvidia/nemotron-3-super-120b-a12b:free",        "provider": "openrouter", "tier": 1},
    {"id": "openai/gpt-oss-120b:free",                      "provider": "openrouter", "tier": 1},
    {"id": "qwen/qwen3-next-80b-a3b-instruct:free",         "provider": "openrouter", "tier": 1},
    {"id": "meta-llama/llama-3.3-70b-instruct:free",        "provider": "openrouter", "tier": 1},
    {"id": "inclusionai/ring-2.6-1t:free",                  "provider": "openrouter", "tier": 1},
    {"id": "google/gemma-4-26b-a4b-it:free",                "provider": "openrouter", "tier": 1},
    
    # --- OpenRouter Tier 2: Mid-range ---
    {"id": "google/gemma-4-31b-it:free",                    "provider": "openrouter", "tier": 2},
    {"id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "provider": "openrouter", "tier": 2},
    {"id": "qwen/qwen3-coder:free",                         "provider": "openrouter", "tier": 2},
    {"id": "nvidia/nemotron-3-nano-30b-a3b:free",           "provider": "openrouter", "tier": 2},
    {"id": "openai/gpt-oss-20b:free",                       "provider": "openrouter", "tier": 2},
    {"id": "minimax/minimax-m2.5:free",                     "provider": "openrouter", "tier": 2},
    {"id": "cognitivecomputations/dolphin-mistral-24b-venice-edition:free", "provider": "openrouter", "tier": 2},
    
    # --- OpenRouter Tier 3: Lightweight Fallbacks ---
    {"id": "nvidia/nemotron-nano-12b-v2-vl:free",           "provider": "openrouter", "tier": 3},
    {"id": "nvidia/nemotron-nano-9b-v2:free",               "provider": "openrouter", "tier": 3},
    {"id": "meta-llama/llama-3.2-3b-instruct:free",         "provider": "openrouter", "tier": 3},
    {"id": "poolside/laguna-m.1:free",                      "provider": "openrouter", "tier": 3},
    {"id": "liquid/lfm-2.5-1.2b-instruct:free",             "provider": "openrouter", "tier": 3},
    {"id": "baidu/cobuddy:free",                            "provider": "openrouter", "tier": 3},
    {"id": "poolside/laguna-xs.2:free",                     "provider": "openrouter", "tier": 3},
    {"id": "z-ai/glm-4.5-air:free",                         "provider": "openrouter", "tier": 3},
    {"id": "liquid/lfm-2.5-1.2b-thinking:free",             "provider": "openrouter", "tier": 3},
]

# ══════════════════════════════════════════════════════════════════════════════
# AGENT-TO-MODEL DISTRIBUTION — each agent starts at a different offset
# so no single model handles all requests at once
# ══════════════════════════════════════════════════════════════════════════════
AGENT_MODEL_ASSIGNMENTS = {
    "ForecastNarrative":    {"start_offset": 0,  "max_tries": 20},  # gemini-2.0-flash first
    "BriefingAgent":        {"start_offset": 0,  "max_tries": 25},  # gemini-2.0-flash first (core)
    "RealtimeIntel":        {"start_offset": 4,  "max_tries": 15},  # gpt-oss-120b first
    "KnowledgeFusion":      {"start_offset": 6,  "max_tries": 15},  # llama-3.3-70b first
    "NLP_EntityExtraction": {"start_offset": 0,  "max_tries": 10},  # gemini-2.0-flash (fast)
    "NLP_BatchExtraction":  {"start_offset": 1,  "max_tries": 10},  # gemini-2.5-flash (fast)
    "RiskSummary":          {"start_offset": 3,  "max_tries": 15},  # nemotron-120b first
    "IntelligenceBriefing": {"start_offset": 2,  "max_tries": 15},  # hermes-405b first
    "StartupInsight":       {"start_offset": 9,  "max_tries": 15},  # gemma-4-31b-it first
    "AdvisoryChat":         {"start_offset": 0,  "max_tries": 25},  # user-facing, maximum resilience
    "DashboardInsight":     {"start_offset": 5,  "max_tries": 10},  # rapid summary
}

# Default fallback for unknown contexts
_DEFAULT_ASSIGNMENT = {"start_offset": 0, "max_tries": 15}

# ══════════════════════════════════════════════════════════════════════════════
# RATE LIMIT TRACKING — per-model 429 cooldown (60s auto-skip)
# ══════════════════════════════════════════════════════════════════════════════
_rate_limit_tracker: dict[str, float] = {}  # model_id -> timestamp of last 429
_RATE_LIMIT_COOLDOWN = 90  # seconds to skip a model after it returns 429
_tracker_lock = threading.Lock()


class ModelState:
    def __init__(self):
        self.switch_count: int = 0
        self.last_switch: str | None = None

_state = ModelState()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def _is_recently_rate_limited(model_id: str) -> bool:
    """Check if a model was rate-limited within the cooldown window."""
    with _tracker_lock:
        last_hit = _rate_limit_tracker.get(model_id)
        if last_hit and (time.time() - last_hit) < _RATE_LIMIT_COOLDOWN:
            return True
        return False


def _mark_rate_limited(model_id: str):
    """Mark a model as recently rate-limited."""
    with _tracker_lock:
        _rate_limit_tracker[model_id] = time.time()
        logger.info(f"[RateLimit] Marked {model_id} as rate-limited for {_RATE_LIMIT_COOLDOWN}s")


def _call_gemini(gemini_client, model_id: str, prompt: str, context: str):
    """Dispatch a call to native Gemini API. Returns text or raises Exception."""
    from backend.core.token_tracker import track_usage
    
    response = gemini_client.models.generate_content(
        model=model_id,
        contents=prompt
    )
    track_usage(response, context=f"{context} [model={model_id}]")
    logger.info(f"[Gemini] {context} completed using {model_id}")
    text = response.text
    if text:
        return text.strip()
    return None


def _call_openrouter(model_id: str, prompt: str, context: str, enable_reasoning: bool = False):
    """Dispatch a call to OpenRouter API. Returns text or raises Exception."""
    from backend.core.token_tracker import track_openrouter_usage
    
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OpenRouter API key not configured")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://adiphas.ai",
        "X-Title": "ADIPHAS Intelligence",
    }
    
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    if enable_reasoning or "hunter" in model_id or "thinking" in model_id:
        payload["reasoning"] = {"enabled": True}
    
    response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    
    if response.status_code == 429:
        _mark_rate_limited(model_id)
        logger.warning(f"[OpenRouter] {model_id} hit 429 for {context}")
        raise RateLimitError(f"429 on {model_id}")
    
    if response.status_code != 200:
        logger.warning(f"[OpenRouter] {model_id} failed with status {response.status_code}: {response.text[:200]}")
        return None
    
    result = response.json()
    if 'choices' in result and len(result['choices']) > 0:
        message = result['choices'][0]['message']
        text = message.get('content') or ""
        
        # Track OpenRouter usage
        usage = result.get('usage', {})
        track_openrouter_usage(
            model_id=model_id,
            prompt_tokens=usage.get('prompt_tokens', 0),
            completion_tokens=usage.get('completion_tokens', 0),
            context=context
        )
        
        if 'reasoning_details' in message and message['reasoning_details']:
            logger.debug(f"[OpenRouter] Reasoning trace received from {model_id} (stripped from output)")
        
        logger.info(f"[OpenRouter] SUCCESS with {model_id} for {context}")
        return text.strip() if text else None
    else:
        logger.warning(f"[OpenRouter] {model_id} returned empty choices for {context}")
        return None


class RateLimitError(Exception):
    """Raised when a model returns a 429 rate limit response."""
    pass


def smart_generate(gemini_client, prompt: str, context: str = "", enable_reasoning: bool = False):
    """
    Unified AI generation across the entire model pool.
    Each agent context starts at a different offset in the pool,
    distributing load so no single model handles all requests.
    
    On 429 errors, models are auto-skipped for 60 seconds.
    Progressive cooldown (2s, 4s, 6s...) between retries.
    """
    assignment = AGENT_MODEL_ASSIGNMENTS.get(context, _DEFAULT_ASSIGNMENT)
    pool_size = len(UNIFIED_MODEL_POOL)
    max_tries = assignment["max_tries"]
    start = assignment["start_offset"]
    
    skipped_count = 0
    
    for i in range(max_tries):
        idx = (start + i) % pool_size
        model_entry = UNIFIED_MODEL_POOL[idx]
        model_id = model_entry["id"]
        provider = model_entry["provider"]
        
        # Skip models that were rate-limited recently
        if _is_recently_rate_limited(model_id):
            logger.debug(f"[SmartGen] Skipping {model_id} (rate-limited cooldown active)")
            skipped_count += 1
            continue
        
        logger.info(f"[SmartGen] {context} → trying {model_id} (attempt {i+1}/{max_tries})")
        
        try:
            if provider == "gemini":
                if not gemini_client:
                    continue
                result = _call_gemini(gemini_client, model_id, prompt, context)
                if result:
                    return result, model_id
            
            elif provider == "openrouter":
                if not OPENROUTER_API_KEY:
                    continue
                result = _call_openrouter(model_id, prompt, context, enable_reasoning)
                if result:
                    return result, f"openrouter/{model_id}"
        
        except RateLimitError:
            # Already marked as rate-limited in _call_openrouter
            cooldown = 2 * (i + 1)
            logger.info(f"[SmartGen] Cooling down {cooldown}s before next model...")
            time.sleep(cooldown)
            continue
        
        except Exception as e:
            error_str = str(e)
            if any(code in error_str for code in ["429", "RESOURCE_EXHAUSTED"]):
                _mark_rate_limited(model_id)
                cooldown = 2 * (i + 1)
                logger.warning(f"[SmartGen] {model_id} rate limited for {context}. Cooling down {cooldown}s...")
                time.sleep(cooldown)
            elif any(code in error_str for code in ["404", "NOT_FOUND"]):
                logger.warning(f"[SmartGen] {model_id} unavailable (404). Skipping.")
            elif "503" in error_str:
                logger.warning(f"[SmartGen] {model_id} service unavailable. Skipping.")
            else:
                logger.error(f"[SmartGen] {model_id} unexpected error for {context}: {e}")
            continue
    
    _state.switch_count += 1
    _state.last_switch = datetime.now().replace(microsecond=0).isoformat()
    logger.error(f"[SmartGen] ALL {max_tries} model attempts exhausted for {context} (skipped {skipped_count} rate-limited).")
    return None, None


# ══════════════════════════════════════════════════════════════════════════════
# EMBEDDING FALLBACK (unchanged — OpenRouter)
# ══════════════════════════════════════════════════════════════════════════════
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
    
    payload = {
        "model": model,
        "input": inputs
    }
    
    try:
        logger.info(f"[OpenRouterEmbed] Attempting fallback using {model}")
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]
        return embeddings
    except Exception as e:
        logger.error(f"[OpenRouterEmbed] Fallback failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# STARTUP VALIDATION — ping each OpenRouter model to confirm availability
# ══════════════════════════════════════════════════════════════════════════════
_validated_models: list[str] = []

def validate_model_pool():
    """
    Called at startup (in a background thread). Pings each OpenRouter model
    with a minimal prompt to check availability. Marks unavailable models
    as rate-limited for the first cycle so they're skipped.
    """
    global _validated_models
    
    if not OPENROUTER_API_KEY:
        logger.warning("[ModelValidation] No OpenRouter API key — skipping validation")
        return
    
    logger.info("[ModelValidation] Starting model pool validation...")
    available = []
    unavailable = []
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://adiphas.ai",
        "X-Title": "ADIPHAS Validation",
    }
    
    for entry in UNIFIED_MODEL_POOL:
        if entry["provider"] != "openrouter":
            available.append(entry["id"])
            continue
        
        model_id = entry["id"]
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,  # Minimal usage
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
            if response.status_code == 200:
                available.append(model_id)
                logger.info(f"[ModelValidation] ✓ {model_id}")
            elif response.status_code == 429:
                # Rate limited but model exists — it's valid but cooling down
                available.append(model_id)
                _mark_rate_limited(model_id)
                logger.info(f"[ModelValidation] ~ {model_id} (exists but rate-limited)")
            else:
                unavailable.append(model_id)
                # Mark as rate-limited for 5 minutes so it's skipped initially
                with _tracker_lock:
                    _rate_limit_tracker[model_id] = time.time() + 240  # extra 4min penalty
                logger.warning(f"[ModelValidation] ✗ {model_id} (status {response.status_code})")
        except Exception as e:
            unavailable.append(model_id)
            logger.warning(f"[ModelValidation] ✗ {model_id} (error: {e})")
        
        time.sleep(1)  # Don't burst the validation pings
    
    _validated_models = available
    logger.info(f"[ModelValidation] Complete: {len(available)}/{len(UNIFIED_MODEL_POOL)} models available, {len(unavailable)} unavailable")


# ══════════════════════════════════════════════════════════════════════════════
# STATUS & LOGGING
# ══════════════════════════════════════════════════════════════════════════════
def get_current_model() -> str:
    """Returns the first model in the pool (for backward compatibility)."""
    return UNIFIED_MODEL_POOL[0]["id"]


def get_model_status_log() -> str:
    """Returns a formatted summary of the unified AI model pool for startup logging."""
    pool_summary = []
    for i, m in enumerate(UNIFIED_MODEL_POOL):
        tier_label = f"T{m['tier']}"
        provider_label = m['provider'].upper()
        pool_summary.append(f"  [{i:2d}] {tier_label} {provider_label}: {m['id']}")
    
    # Show agent assignments
    agent_summary = []
    for agent, cfg in AGENT_MODEL_ASSIGNMENTS.items():
        start_model = UNIFIED_MODEL_POOL[cfg['start_offset'] % len(UNIFIED_MODEL_POOL)]['id']
        agent_summary.append(f"  {agent}: offset={cfg['start_offset']} → {start_model} (max {cfg['max_tries']} tries)")
    
    status = [
        "\n" + "="*60,
        "ADIPHAS INTELLIGENCE: UNIFIED MODEL POOL",
        "="*60,
        f"Total Models: {len(UNIFIED_MODEL_POOL)}",
        f"Gemini Native: {sum(1 for m in UNIFIED_MODEL_POOL if m['provider'] == 'gemini')}",
        f"OpenRouter Free: {sum(1 for m in UNIFIED_MODEL_POOL if m['provider'] == 'openrouter')}",
        f"OpenRouter Fallback: {'ENABLED' if OPENROUTER_API_KEY else 'DISABLED (Check .env)'}",
        "",
        "Model Pool:",
        "\n".join(pool_summary),
        "",
        "Agent Assignments:",
        "\n".join(agent_summary),
        "",
        f"Rate Limit Cooldown: {_RATE_LIMIT_COOLDOWN}s per model",
        f"Total Exhaustion Events: {_state.switch_count}",
        "="*60 + "\n"
    ]
    return "\n".join(status)


def get_model_status() -> dict:
    """Returns the current unified model pool status."""
    # Count currently rate-limited models
    now = time.time()
    with _tracker_lock:
        rate_limited = [
            model_id for model_id, ts in _rate_limit_tracker.items()
            if (now - ts) < _RATE_LIMIT_COOLDOWN
        ]
    
    return {
        "pool_size": len(UNIFIED_MODEL_POOL),
        "model_pool": [
            {
                "id": m["id"],
                "provider": m["provider"],
                "tier": m["tier"],
                "rate_limited": m["id"] in rate_limited
            }
            for m in UNIFIED_MODEL_POOL
        ],
        "agent_assignments": AGENT_MODEL_ASSIGNMENTS,
        "rate_limited_models": rate_limited,
        "exhaustion_count": _state.switch_count,
        "last_exhaustion": _state.last_switch,
        "openrouter_enabled": bool(OPENROUTER_API_KEY),
        "validated_models": _validated_models,
    }
