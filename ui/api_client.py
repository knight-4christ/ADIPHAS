import requests
import os

# Default to localhost for local dev
API_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

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
    return _safe_request("POST", f"{API_URL}/idsr/upload", files=files)

def get_alerts():
    return _safe_request("GET", f"{API_URL}/alerts/list")

def assess_symptoms(payload):
    return _safe_request("POST", f"{API_URL}/symptom/assess", json=payload)

def get_forecast(lga_code, disease):
    payload = {"lga_code": lga_code, "disease": disease, "lookahead_weeks": 4}
    return _safe_request("POST", f"{API_URL}/predict/forecast", json=payload)

def scrape_news():
    return _safe_request("GET", f"{API_URL}/acquisition/news/scrape")

def fuse_intelligence(reports):
    return _safe_request("POST", f"{API_URL}/intelligence/fuse", json=reports)

def register(username, password, email=None, full_name=None, role="CITIZEN"):
    payload = {
        "username": username,
        "password": password,
        "email": email,
        "full_name": full_name,
        "role": role
    }
    return _safe_request("POST", f"{API_URL}/auth/register", json=payload)

def login(username, password):
    payload = {
        "username": username,
        "password": password
    }
    # Using data instead of json for OAuth2 form format
    return _safe_request("POST", f"{API_URL}/auth/login", data=payload)

def get_me(token):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("GET", f"{API_URL}/users/me", headers=headers)

def update_profile(token, profile_data):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("PUT", f"{API_URL}/users/profile", json=profile_data, headers=headers)

def get_activity():
    return _safe_request("GET", f"{API_URL}/system/activity")

def get_activity_history(date_str):
    return _safe_request("GET", f"{API_URL}/system/activity/history", params={"date_str": date_str})

def verify_alert(token, alert_id):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("POST", f"{API_URL}/alerts/{alert_id}/verify", headers=headers)

def get_users(token):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("GET", f"{API_URL}/users/list", headers=headers)

def delete_user(token, user_id):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("DELETE", f"{API_URL}/users/{user_id}", headers=headers)

def discard_alert(token, alert_id):
    headers = {"Authorization": f"Bearer {token}"}
    return _safe_request("DELETE", f"{API_URL}/alerts/{alert_id}", headers=headers)

# --- Evaluation Endpoints ---

def get_evaluation_metrics():
    return _safe_request("GET", f"{API_URL}/api/evaluation/metrics")

def get_evaluation_samples():
    return _safe_request("GET", f"{API_URL}/api/evaluation/samples")

def submit_evaluation(payload):
    return _safe_request("POST", f"{API_URL}/api/evaluation/submit", json=payload)

def get_briefing(lga=None, role="CITIZEN"):
    return _safe_request("GET", f"{API_URL}/intelligence/briefing", params={"lga": lga, "role": role})

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
    return _safe_request("GET", f"{API_URL}/idsr/history", params=params)
def advisory_search(query, k=3):
    """Performs a Hybrid RAG search (Chroma + Tavily) via the backend."""
    return _safe_request("GET", f"{API_URL}/api/advisory/search", params={"query": query, "k": k})

def get_intelligence_sources():
    """Returns the dictionary of monitored sources and their weights from the backend."""
    return _safe_request("GET", f"{API_URL}/intelligence/sources")
