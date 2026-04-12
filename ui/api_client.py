import requests  # type: ignore[import-untyped]
import os
import time
from datetime import datetime
import streamlit as st

# Try Streamlit Secrets first, then OS environment, then fallback to localhost
try:
    API_URL = st.secrets.get("BACKEND_URL", os.getenv("BACKEND_URL", "http://localhost:8000"))
except Exception:
    API_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ── Client-side TTL cache to prevent redundant polling ──
_cache: dict = {}
_DEFAULT_CACHE_TTL = 30  # seconds

def _cached_request(cache_key: str, method: str, url: str, ttl: int = _DEFAULT_CACHE_TTL, **kwargs):
    """Returns cached response if available and fresh, otherwise makes a new request."""
    now = time.time()
    if cache_key in _cache and (now - _cache[cache_key]["time"]) < ttl:
        return _cache[cache_key]["data"]
    data = _safe_request(method, url, **kwargs)
    _cache[cache_key] = {"data": data, "time": now}
    return data

def time_ago(iso_str: str) -> str:
    """Converts an ISO timestamp into a human-readable 'time ago' string."""
    if not iso_str: return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        # If naive, assume UTC (backend operates in UTC)
        if dt.tzinfo is None:
            now = datetime.utcnow()
        else:
            from datetime import timezone
            now = datetime.now(timezone.utc)
            
        diff = now - dt
        seconds = diff.total_seconds()
        
        if seconds < 60: return "Just now"
        if seconds < 3600: return f"{int(seconds // 60)}m ago"
        if seconds < 86400: return f"{int(seconds // 3600)}h ago"
        if seconds < 172800: return "Yesterday"
        return f"{int(seconds // 86400)}d ago"
    except Exception:
        return str(iso_str).split('T')[0]

def _safe_request(method, url, **kwargs):
    """Internal helper to handle requests and catch non-JSON responses."""
    try:
        response = requests.request(method, url, **kwargs)
        try:
            data = response.json()
            # If the response itself is an error from FastAPI, pass it along
            if response.status_code >= 400 and not data.get("detail"):
                data["detail"] = f"HTTP Error {response.status_code}"
            return data
        except requests.exceptions.JSONDecodeError:
            return {
                "error": True,
                "status_code": response.status_code,
                "detail": "Server returned a non-JSON response.",
                "raw": response.text[:500]
            }
    except Exception as e:
        return {
            "error": True,
            "status_code": 500,
            "detail": f"Connection Error: {str(e)}"
        }

def healthcheck():
    return _safe_request("GET", f"{API_URL}/healthcheck")

def upload_idsr(file):
    files = {"file": file}
    return _safe_request("POST", f"{API_URL}/api/data/idsr_upload", files=files)

def get_alerts():
    return _cached_request("ebs_list", "GET", f"{API_URL}/api/ebs/list", ttl=30)

def assess_symptoms(payload):
    return _safe_request("POST", f"{API_URL}/api/advisory/symptom_check", json=payload)

def get_forecast(lga_code, disease):
    payload = {"lga_code": lga_code, "disease": disease, "lookahead_weeks": 4}
    return _safe_request("POST", f"{API_URL}/api/data/forecast", json=payload)

def scrape_news():
    return _safe_request("GET", f"{API_URL}/api/acquisition/news/scrape")

def fuse_intelligence(reports):
    return _safe_request("POST", f"{API_URL}/api/intelligence/fuse", json=reports)

def register(username, password, email=None, full_name=None, role="CITIZEN", location_lga=None):
    payload = {
        "username": username,
        "password": password,
        "email": email,
        "full_name": full_name,
        "role": role,
        "location_lga": location_lga
    }
    return _safe_request("POST", f"{API_URL}/api/auth/register", json=payload)

def login(username, password):
    payload = {
        "username": username,
        "password": password
    }
    # Using data instead of json for OAuth2 form format
    return _safe_request("POST", f"{API_URL}/api/auth/login", data=payload)

def get_me(token):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("GET", f"{API_URL}/api/users/me", headers=headers)

def update_profile(token, profile_data):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("PUT", f"{API_URL}/api/users/profile", json=profile_data, headers=headers)

def get_activity():
    return _safe_request("GET", f"{API_URL}/api/system/activity")

def get_activity_history(date_str):
    return _safe_request("GET", f"{API_URL}/api/system/activity/history", params={"date_str": date_str})

def verify_alert(token, alert_id):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("POST", f"{API_URL}/api/ebs/{alert_id}/verify", headers=headers)

def get_users(token):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("GET", f"{API_URL}/api/users/list", headers=headers)

def delete_user(token, user_id):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("DELETE", f"{API_URL}/api/users/{user_id}", headers=headers)

def discard_alert(token, alert_id):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("DELETE", f"{API_URL}/api/ebs/{alert_id}", headers=headers)

# --- Evaluation Endpoints ---

def get_evaluation_metrics():
    return _safe_request("GET", f"{API_URL}/api/evaluation/metrics")

def get_evaluation_samples():
    return _safe_request("GET", f"{API_URL}/api/evaluation/samples")

def submit_evaluation(payload):
    return _safe_request("POST", f"{API_URL}/api/evaluation/submit", json=payload)

def get_briefing(lga=None, role="CITIZEN"):
    return _safe_request("GET", f"{API_URL}/api/intelligence/briefing", params={"lga": lga, "role": role})

def nlp_extract(text):
    """Extracts disease/location entities from raw text via the backend NLP agent."""
    return _safe_request("POST", f"{API_URL}/api/nlp/extract", json={"text": text})

def get_idsr_history(lga_code=None, disease=None):
    """Returns weekly IDSR case counts from the DB for historical chart rendering."""
    params = {}
    if lga_code:
        params["lga_code"] = lga_code
    if disease:
        params["disease"] = disease
    return _safe_request("GET", f"{API_URL}/api/data/idsr_history", params=params)
def advisory_search(query, k=3, force_combine=True):
    """Performs a Hybrid RAG search (Chroma + Tavily) via the backend."""
    return _safe_request("GET", f"{API_URL}/api/advisory/search", params={"query": query, "k": k, "force_combine": force_combine})

def advisory_chat(messages, token, enable_reasoning=False, context="", location=""):
    """Sends chat history and search context to the backend for bio-aware reasoning."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "messages": messages,
        "enable_reasoning": enable_reasoning,
        "context": context,
        "location": location
    }
    return _safe_request("POST", f"{API_URL}/api/advisory/chat", json=payload, headers=headers)

def get_dashboard_insight(token, location, alerts_summary=""):
    """Fetches a rapid tailored insight for the user's dashboard."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "location": location,
        "alerts_summary": alerts_summary
    }
    return _safe_request("POST", f"{API_URL}/api/advisory/dashboard_insight", json=payload, headers=headers)

def trigger_manual_briefing():
    """Triggers a manual StAMP intelligence cycle via the backend."""
    return _safe_request("POST", f"{API_URL}/api/system/briefing/trigger")

def get_intelligence_sources():
    """Returns the dictionary of monitored sources and their weights from the backend."""
    return _safe_request("GET", f"{API_URL}/api/intelligence/sources")

def get_startup_insight():
    """Returns the one-time AI startup insight."""
    return _safe_request("GET", f"{API_URL}/system/startup-insight")

def get_token_usage():
    """Returns current Gemini API token usage for this session."""
    return _safe_request("GET", f"{API_URL}/system/token-usage")

def get_system_metrics():
    """Returns today's scraping and intelligence metrics."""
    return _safe_request("GET", f"{API_URL}/api/system/metrics")

def get_model_status():
    """Returns the current unified model pool status."""
    return _cached_request("model_status", "GET", f"{API_URL}/system/model-status", ttl=30)

def get_latest_briefing():
    """Returns the most recent system-wide autonomous briefing snapshot."""
    return _cached_request("briefing", "GET", f"{API_URL}/system/briefing", ttl=60)
