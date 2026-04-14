# ADIPHAS: Production Deployment & Hosting Guide

This guide documents the complete production deployment pipeline for ADIPHAS, including the live cloud architecture, environment configuration, and operational maintenance procedures.

---

## 1. Production Architecture (Live)

ADIPHAS runs on a **split-cloud architecture** with two independently hosted services:

| Component | Platform | URL |
|---|---|---|
| **Backend API** | [Render](https://render.com) (Native Python 3.11) | `https://adiphas.onrender.com` |
| **Frontend UI** | [Streamlit Community Cloud](https://streamlit.io/cloud) | `https://adiphas.streamlit.app` |
| **Database** | [Neon PostgreSQL](https://neon.tech) | Connected via `DATABASE_URL` |
| **Geocoding Chain** | Nominatim, BigDataCloud, ipapi.co | Zero-config free APIs for location resilience |

### How It Works
1. The **Streamlit frontend** reads the `BACKEND_URL` from Streamlit Secrets (`st.secrets`).
2. All API calls (authentication, data retrieval, intelligence queries) are routed to the **Render backend**.
3. The backend connects to the **Neon PostgreSQL** database for persistent storage.
4. Background AI agents run autonomously on the Render instance via APScheduler.

```
┌─────────────────┐     HTTPS      ┌──────────────────┐     SQL       ┌────────────────┐
│  Streamlit Cloud │ ──────────►  │  Render Backend   │ ──────────►  │  Neon Postgres  │
│  (UI / Frontend) │  ◄──────────  │  (FastAPI + AI)   │  ◄──────────  │  (Database)     │
└─────────────────┘    JSON API    └──────────────────┘   psycopg2    └────────────────┘
```

---

## 2. Render Backend Configuration

### 2.1 Service Settings (Render Dashboard)
| Setting | Value |
|---|---|
| **Runtime** | Python 3.11 (Native) |
| **Root Directory** | _(leave blank — uses repo root)_ |
| **Build Command** | `pip install -r backend/requirements.txt` |
| **Start Command** | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |

### 2.2 Environment Variables (Render Dashboard → Environment)

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ Yes | Random string for JWT token signing. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | ✅ Yes | Neon PostgreSQL connection string (e.g., `postgresql://user:pass@host/db?sslmode=require`) |
| `GEMINI_API_KEY` | ✅ Yes | Google AI Studio API key for Gemini models |
| `OPENROUTER_API_KEY` | ⚠️ Recommended | OpenRouter API key for fallback AI models |
| `TAVILY_API_KEY` | Optional | Tavily Search API key for real-time web intelligence |
| `PYTHON_VERSION` | ✅ Yes | Set to `3.11.12` |

### 2.3 render.yaml Blueprint
```yaml
services:
  - type: web
    name: adiphas
    runtime: python
    buildCommand: pip install -r backend/requirements.txt
    startCommand: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: SECRET_KEY
        sync: false
      - key: DATABASE_URL
        sync: false
      - key: GEMINI_API_KEY
        sync: false
      - key: OPENROUTER_API_KEY
        sync: false
      - key: TAVILY_API_KEY
        sync: false
```

---

## 3. Streamlit Frontend Configuration

### 3.1 Streamlit Cloud Settings
| Setting | Value |
|---|---|
| **Repository** | `github.com/<your-user>/ADIPHAS` |
| **Branch** | `master` |
| **Main module** | `ui/app.py` |
| **Python version** | `3.11` (enforced via `.python-version` file) |

### 3.2 Streamlit Secrets (Settings → Secrets)
```toml
BACKEND_URL = "https://adiphas.onrender.com"
```

### 3.3 How the Frontend Reads the Backend URL
The `ui/api_client.py` module uses a priority chain to resolve the backend URL:
```python
# Priority: st.secrets → os.environ → localhost fallback
try:
    API_URL = st.secrets.get("BACKEND_URL", os.getenv("BACKEND_URL", "http://localhost:8000"))
except Exception:
    API_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
```

### 3.4 UI Theme Configuration
Dark theme is enforced via `ui/.streamlit/config.toml`:
```toml
[theme]
primaryColor = "#00C9A7"
backgroundColor = "#0E1117"
secondaryBackgroundColor = "#1A1A2E"
textColor = "#E0E0E0"
```

---

## 4. Database (Neon PostgreSQL)

### 4.1 Connection
- **Provider:** Neon (serverless PostgreSQL)
- **Driver:** `psycopg2-binary`
- **Connection Pooling:** Configured in `backend/database.py` with `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`

### 4.2 Schema Auto-Migration
Tables are created automatically on startup via SQLAlchemy:
```python
models.Base.metadata.create_all(bind=engine)
```

### 4.3 Primary Key Sequence Fix (Post-Migration)
When migrating data from SQLite to PostgreSQL, auto-increment sequences can become desynchronized. Run the included `db_fix.py` script locally to repair:
```bash
python db_fix.py
```
This resets the `SERIAL` sequences for all tables (`system_activities`, `idsr_records`, `autonomous_snapshots`, `predictive_snapshots`, `evaluation_samples`) to `MAX(id) + 1`.

---

## 5. Authentication System

### 5.1 Password Hashing
ADIPHAS uses **native `bcrypt`** (not `passlib`) for password hashing to avoid the known `passlib` 72-byte wrap bug on modern `bcrypt>=4.x` backends:
```python
import bcrypt
bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
```

### 5.2 JWT Tokens
- **Algorithm:** HS256
- **Expiry:** 30 minutes (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Library:** `python-jose[cryptography]`

---

## 6. AI Model Configuration

### 6.1 Primary Chain (Google Gemini)
```python
MODEL_CHAIN = ["gemini-2.0-flash", "gemini-2.5-flash"]
```
Gemini is the primary AI engine. When one model hits a 429 rate limit, the system automatically switches to the next.

### 6.2 Fallback Chain (OpenRouter Free Tier)
When all Gemini models are exhausted, ADIPHAS engages the OpenRouter fallback tier with **9 verified free models** (updated 2026-04-09):

| Priority | Model ID | Size |
|---|---|---|
| 1 | `google/gemma-4-31b-it:free` | 31B |
| 2 | `nvidia/nemotron-3-super-120b-a12b:free` | 120B |
| 3 | `qwen/qwen3-coder:free` | 480B MoE |
| 4 | `openai/gpt-oss-120b:free` | 120B |
| 5 | `nousresearch/hermes-3-llama-3.1-405b:free` | 405B |
| 6 | `google/gemma-3-27b-it:free` | 27B |
| 7 | `meta-llama/llama-3.3-70b-instruct:free` | 70B |
| 8 | `meta-llama/llama-3.2-3b-instruct:free` | 3B |
| 9 | `minimax/minimax-m2.5:free` | — |

### 6.3 Rate Limit Budget (Free Tier)
- **OpenRouter Free Tier:** ~50 requests/day per model, ~20 requests/minute
- **Scheduler Interval:** Set to **120 minutes (2 hours)** to stay within daily limits
- **Effective capacity:** ~12 cycles/day × ~4-5 AI calls = safely under 50 daily requests
- **To increase capacity:** Add $5-10 credits on [OpenRouter](https://openrouter.ai/settings/credits)

---

## 7. Background Scheduler (APScheduler)

### 7.1 Autonomous Monitoring Job
Runs every **2 hours** (configurable in `backend/scheduler.py`):
1. **Scout Phase:** Scrapes 20+ news sources via Scrapling
2. **NLP Phase:** Extracts disease/location entities via spaCy + Gemini batch
3. **Fusion Phase:** Reconciles signals using Dempster-Shafer
4. **Vectorization:** Indexes new alerts into the Titan Vector Engine
5. **Predictive Phase:** Updates forecast snapshots for all LGA/disease pairs
6. **Verification Phase:** Auto-verifies high-confidence fused alerts
7. **Realtime Intel Phase:** Fetches live web signals via Tavily (self-throttles to every 6h)
8. **Briefing Phase:** Generates daily StAMP intelligence briefing (self-throttles to every 24h)

### 7.2 Startup Sequence
On cold start, the system:
1. Starts the APScheduler background thread
2. Runs SQLite self-healing migrations (if applicable)
3. Launches `StartupInsight` generation in a separate thread (30s delay)
4. Launches the first monitoring cycle in a separate thread (60s delay)
5. Starts a liveness heartbeat logger (every 5 minutes)

### 7.3 Keep-Alive (Render Free Tier)
Render's free tier spins down after 15 minutes of inactivity. To prevent this:
1. Go to [cron-job.org](https://cron-job.org)
2. Create a job to `GET https://adiphas.onrender.com/healthcheck` every **14 minutes**
3. This keeps the instance warm and the scheduler running continuously

---

## 8. Local Development

### 8.1 Quick Start (Windows PowerShell)
```powershell
.\start_adiphas.ps1
```

### 8.2 Quick Start (Linux/macOS)
```bash
chmod +x start_adiphas.sh
./start_adiphas.sh
```

### 8.3 Manual Start
```bash
# Terminal 1: Backend
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
streamlit run ui/app.py
```

### 8.4 Local Environment Variables
Create a `.env` file in the project root (see `.env.template` for reference):
```env
SECRET_KEY=your-local-dev-secret
DATABASE_URL=sqlite:///./data/data.db
GEMINI_API_KEY=your_gemini_key
OPENROUTER_API_KEY=your_openrouter_key
TAVILY_API_KEY=your_tavily_key
```

---

## 9. Security Checklist (Production)
- [ ] Rotate all API keys after initial deployment
- [ ] Ensure `SECRET_KEY` is a cryptographically random string (≥32 bytes)
- [ ] Verify `.env` is in `.gitignore` (never commit secrets)
- [ ] Enable CORS restrictions in `backend/main.py` (currently `allow_origins=["*"]`)
- [ ] Set up rate limiting on registration endpoint (already configured: 5/minute)
- [ ] Monitor Render logs for `UniqueViolation` errors (indicates sequence desync)

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Signup Failed: Connection Error localhost:8000` | Frontend not reading `BACKEND_URL` | Check Streamlit Secrets in Cloud settings |
| `Server returned non-JSON response` | Backend crashing with 500 | Check Render logs for traceback |
| `password cannot be longer than 72 bytes` | `passlib` wrap bug | Replace with native `bcrypt` (already fixed) |
| `duplicate key value violates unique constraint` | PostgreSQL sequence desync | Run `python db_fix.py` locally |
| `EVERY intelligence path exhausted` | All AI models rate-limited | Wait for quota reset or add OpenRouter credits |
| `FAILED_PRECONDITION: User location not supported` | Gemini embedding blocked in region | System auto-falls back to OpenRouter embeddings |
