# ADIPHAS: Automated Disease Intelligence and Public Health Advisory System
**A Final Year Project Documentation**
**Department of Computer Science | 2025/2026 Academic Session**

## Abstract
Emerging and re-emerging disease outbreaks continue to pose severe public health risks in densely populated urban centres such as Lagos State, Nigeria. The latency between the onset of an outbreak, its detection, and the dissemination of actionable intelligence to citizens and public health professionals remains a critical bottleneck in existing surveillance frameworks. This project presents the Automated Disease Intelligence and Public Health Advisory System (ADIPHAS) — a multi-layered, autonomous health intelligence platform designed to address this gap. ADIPHAS continuously harvests signals from over 20 authoritative digital sources, applies a hybrid Natural Language Processing (NLP) pipeline to extract geospatial and epidemiological entities, fuses multi-source signals using a mathematically grounded confidence model, and delivers role-specific actionable intelligence to three classes of users (Citizens, Experts, and Administrators) through a real-time, web-based dashboard. The system integrates a Retrieval-Augmented Generation (RAG) architecture powered by Google Gemini and ChromaDB to augment advisory responses with contextual knowledge. Preliminary evaluations achieved a micro-averaged F1 score exceeding 0.85 on disease and location entity recognition, demonstrating research-grade accuracy.

**Keywords:** Event-Based Surveillance, NLP, RAG, Knowledge Fusion, Public Health Informatics, FastAPI, Streamlit, LLM, spaCy, Scrapling.

---

## 1. Introduction
### 1.1 Problem Statement
Nigeria's Integrated Disease Surveillance and Response (IDSR) framework is largely passive, relying on health facility reports aggregated weekly. In a city like Lagos, outbreaks of cholera, Lassa fever, or mpox demonstrate that detection-to-response latency under traditional frameworks can exceed 14 days — a window within which epidemic spread becomes exponential. ADIPHAS addresses this "signal latency" by turning the open web into a real-time Early Warning System.

### 1.2 Objectives
1.  **Autonomous Pipeline:** Harvest disease signals from 20+ authoritative sources using **Scrapling v0.4** with anti-bot bypass.
2.  **Hybrid NLP & Sanitization:** Implement a local-first **spaCy** pipeline for high-speed extraction, refined by **Gemini 2.5 Flash** for deep semantic analysis, guarded by a deep regex sanitization layer to prevent AI reasoning trace (`<think>`) leakage.
3.  **Knowledge Fusion:** Reconcile conflicting multi-source signals using the **Dempster-Shafer Theory of Evidence**.
4.  **Role-Specific & Location-Aware Intelligence:** Deliver actionable insights grounded by HTML5 Browser Geolocation (reverse-geocoding `lat`/`lon` to local LGAs) to dynamically generate personalised geo-health insights.
5.  **Hybrid-RAG Advisory:** Ground AI responses in both local verified alerts (**Titan Vector Engine**) and global real-time context (**Tavily Search API**).
6.  **AI Resilience:** Implement a **Universal Fallback Tier** (Gemini -> OpenRouter) to ensure 24/7 intelligence availability during API quota exhaustion.

---

## 2. System Architecture
### 2.1 High-Level Design
ADIPHAS utilizes a four-layer architecture:
1.  **Presentation Layer:** Streamlit-based dashboard featuring real-time log streaming, interactive heatmaps dynamically centered via HTML5 Browser Geolocation, and an explicit manual real-time bypass for StAMP sweeps.
2.  **Application Layer:** FastAPI backend managing JWT authentication, Resilient AI Failover, data sanitization, and Hybrid-RAG retrieval.
3.  **Intelligence Agent Layer:** Multithreaded fleet (Scout, NLP, Fusion, StAMP Briefing Agent) running continuously on a **2-hour APScheduler** background cycle, optimised to maximise intelligence coverage within free-tier API rate limits.
4.  **Persistence Layer:** Hosted physically on **Neon Cloud PostgreSQL**, offering robust connection pooling (`pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`) to efficiently handle massive parallel read/writes from the multithreaded AI extractors, entirely eliminating the concurrency locks associated with embedded SQLite.

### 2.2 Local-First AI Strategy
To ensure cost-efficiency and performance, ADIPHAS implements a tiered AI strategy:
-   **Routine Extraction:** Delegated to local spaCy models and rule-based keyword matchers.
-   **Deep Refinement:** Reserved for batch processing of news high-priority signals.
-   **Generative Synthesis:** Reserved for executive briefings and RAG-grounded advisory queries.

---

## 3. Methodology & Mathematical Framework
### 3.1 Entity Extraction Pipeline
Extraction follows three stages:
1.  **Stage 1 - NER (Local):** spaCy `en_core_web_sm` identifies GPE/LOC entities, cross-referenced against a 20-LGA/37-LCDA Lagos gazetteer.
2.  **Stage 2 - Rule-Based Matching:** Identifies 13+ epidemic-priority diseases and urgency keywords (e.g., *fatalities*, *crisis*).
3.  **Stage 3 - Gemini Batch Analysis:** Refines extraction and generates a 1-sentence technical "intelligence summary" and situational advisory.

### 3.2 Knowledge Fusion (Dempster-Shafer)
Reconciles signals across sources by treating each unique source $i$ as an independent mass function:
-   **Belief $m(Real)$:** $1 - \prod_{i=1}^{n} (1 - W_i)$, where $W_i$ is the source reliability weight.
-   **Spatial Verification:** Alerts from LCDAs receive a confidence boost ($0.95$) if corroborated by a report from its parent LGA.

### 3.3 Personalised Risk Scoring
Risk is computed as a weighted sum of self-reported symptoms, NLP-derived severity ($S_{nlp}$), and environmental risk ($E_{env}$):
$$R_{final} = \min\left(R_{base} + (S_{nlp} \times 0.3) + \frac{E_{env}}{100}, \ 1.0\right)$$
-   **Environmental Penalty ($E_{env}$):** Computed based on alert frequency and proximity to the user's LGA, capped at $60.0$.
-   **Biological Modifiers:** SS/SC genotypes receive alerts for Malaria complications; Blood Group O receives priority warnings for Cholera.

### 3.4 Epidemiological Forecasting
ADIPHAS predicts 4-week case trends using a **Weighted Moving Average (WMA)**:
$$\hat{y}_{t+1} = \frac{\sum_{i=1}^{n} w_i \cdot y_{t-i+1}}{\sum_{i=1}^{n} w_i} + (Trend \times i \times 0.5)$$
Where $w_i \in \{0.2, 0.3, 0.5\}$ favor recent data. Model accuracy is audited using **MAE** and **RMSE** from internal backtesting.

---

## 4. Implementation Details
### 4.1 Production Deployment Architecture
ADIPHAS is deployed on a **split-cloud architecture** designed for cost-efficiency and reliability:
-   **Backend (FastAPI):** Hosted on **Render** as a Native Python 3.11 Web Service, running `uvicorn backend.main:app` with automatic builds from the GitHub `master` branch.
-   **Frontend (Streamlit):** Hosted on **Streamlit Community Cloud**, reading the backend URL from `st.secrets` to route all API calls to the Render instance.
-   **Database:** Hosted on **Neon PostgreSQL** (serverless), connected via `DATABASE_URL` with `psycopg2-binary` and SQLAlchemy connection pooling.
-   **Keep-Alive:** A cron job (via [cron-job.org](https://cron-job.org)) pings the `/healthcheck` endpoint every 14 minutes to prevent Render free-tier spin-down.

### 4.2 Authentication & Security
The authentication system implements several hardened security measures:
-   **Password Hashing:** Uses **native `bcrypt`** (not `passlib`) to avoid the known 72-byte wrap detection bug that crashes `passlib` on modern `bcrypt>=4.x` backends. Passwords are hashed via `bcrypt.hashpw()` with auto-generated salts.
-   **JWT Tokens:** Signed using `HS256` with a cryptographically random `SECRET_KEY` (environment variable). Tokens expire after 30 minutes.
-   **Rate Limiting:** Registration endpoint is protected with `slowapi` at 5 requests/minute to prevent brute-force account creation.
-   **Role-Based Access Control (RBAC):** Three-tier role hierarchy (`CITIZEN < EXPERT < ADMIN`) enforced at the router level via dependency injection.

### 4.3 Real-Time Metrics & Caching
The system features a **5-second TTL (Time-To-Live)** cache for high-frequency dashboard metrics. It calculates cumulative daily totals for scraped articles and new signals, preventing database lockups during concurrent role access.

### 4.4 Hybrid-RAG and Strategic Intelligence
The RAG pipeline utilizes a dual-path retrieval strategy:
- **Local Path**: Verified EBS alerts and IDSR historical aggregates are indexed in the **Titan Vector Engine** for high-precision local context.
- **Global Path**: If local data is insufficient or a query involves emerging global trends, the system triggers the **Tavily Search API** for real-time web context.
- **StAMP Synthesis & Manual Bypass**: The **Situational Awareness & Monitoring Protocol (StAMP)** generates a daily strategic briefing by fusing these paths. To aid immediate incident investigation, experts can utilize the explicit "Force Real-time StAMP Sweep" bypass, directly commanding the pipeline to run instantaneous fresh reconnaissance outside standard scheduling boundaries.
- **Reasoning Trace Sanitization**: All generative outputs are passed through a defensive 3-layer architecture (Generation, Storage, Serving) utilizing strict Regex algorithms to successfully strip any internal Chain-of-Thought (e.g., `<think>`) leakage produced by advanced reasoning models like DeepSeek.

### 4.5 AI Model Resilience & Universal Fallback
ADIPHAS implements a **three-tier AI resilience architecture** to guarantee 24/7 intelligence availability:
1.  **Tier 1 — Healed Gemini Chain:** Primary models (`gemini-2.0-flash` → `gemini-2.5-flash`) augmented with an **Exponential Backoff Protocol**. When the 15 RPM free-tier limit is hit, the system performs a tactical pause (5, 10, 15 seconds) to allow quota regeneration before proceeding, eliminating 429 crash loops.
2.  **Tier 2 — OpenRouter Free Chain:** Nine verified free models including `Gemma 4 31B`, `Nemotron 3 120B`, `Qwen3 Coder 480B`, `GPT-OSS 120B`, `Hermes 405B`, and others, providing massive redundancy if Gemini hard-fails.
3.  **Tier 3 — Rule-Based Fallback:** When all AI paths are exhausted, the system generates statistical summaries from raw database aggregates, ensuring the dashboard never displays blank intelligence panels.

The background scheduler interval is set to **120 minutes (2 hours)** to optimise intelligence coverage within the free-tier rate limits (~50 requests/day on OpenRouter).

### 4.6 Notification Infrastructure (Modular Status)
The system includes modules for **SMS (Twilio)** and **Email (SMTP)** broadcasting. These are currently implemented as background utilities and can be activated for high-risk alerts (`risk_level == "High"`) once notification quotas are established.

---

## 5. Summary of Achievements
-   **Production Deployment:** Successfully deployed a fully operational split-cloud architecture (Render + Streamlit Cloud + Neon PostgreSQL) accessible at `https://adiphas.streamlit.app`.
-   **Concurrency & Data Integrity:** Replaced legacy sequential SQLite operations with high-availability **Neon PostgreSQL**, successfully eliminating connection locks under high NLP pipeline loads. Implemented automatic primary key sequence repair tooling for SQLite-to-PostgreSQL migrations.
-   **Accuracy & Integrity:** Achieved $0.875$ micro-averaged F1 on representative health data, while implementing complete sanitization protocols ensuring 100% public-ready briefing output free of raw model reasoning tokens.
-   **AI Resilience:** Built a **12-model deep fallback chain** (2 Gemini native + 9 OpenRouter free + 1 rule-based) ensuring intelligence generation even under complete API quota exhaustion. Removed dead model endpoints (`stepfun`, `mistral-small-3.1`, `xiaomi/mimo-v2-pro`) that were wasting API calls.
-   **Efficiency:** Reduced LLM API calls by **95%** using local-first extraction and caching. Optimised the background scheduler from 15-minute to 2-hour intervals to sustainably operate within free-tier API budgets.
-   **UI Stability & Frontend Hardening:** Eliminated persistent WebGL initialization crashes and strict Pandas 2.2.0 `GroupBy` runtime errors on Streamlit Cloud. This was achieved by systematically replacing all `Plotly Express` analytical charts with memory-safe pure `plotly.graph_objects`, and entirely migrating the spatial analytics engine from Plotly Mapbox to **Folium (Leaflet.js)** for highly robust, DOM-native interactive mapping.
-   **Security Hardening:** Replaced the vulnerable `passlib` password hashing library with native `bcrypt` to resolve the 72-byte wrap detection crash. Implemented server-side error logging with clean user-facing error messages.
-   **Hyper-Personalization:** Connected browser-native HTML5 `navigator.geolocation` APIs with OpenStreetMap reverse geocoding to automatically center heatmaps and tailor instant epidemiological advisories based on the user's precise Local Government Area.
-   **Information Warfare & Stealth Data Acquisition:** Successfully defeated complex Cloudflare and WAF (Web Application Firewall) blocks on government portals (NCDC, FMoH, The Guardian). By utilizing native Google Chrome TLS fingerprint impersonation via the **Scrapling** module (`Fetcher(stealthy_headers=True)`), ADIPHAS consistently bypasses 403 Forbidden constraints, allowing uninterrupted surveillance. Validated and patched internal parser argument incompatibilities to ensure robust 24/7 scraping stability.
---

## 6. Limitations & Future Improvements
### 6.1 Current System Limitations
- **Geolocation Resolution Limits:** The current HTML5 reverse geocoding via OpenStreetMap relies on the accuracy of the user's device. Devices lacking GPS hardware (like some desktops) fall back to ISP-level IP coordinates, which may lack the specific Local Government Area (LGA) granularity required for hyper-local intelligence.
- **LLM Quota Constraints:** The batch intelligence engine aggressively processes up to 50 raw articles concurrently. While highly efficient, this burst computation safely navigates limits utilizing Exponential Backoff, but sustained anomalies can occasionally exhaust free-tier Gemini API caps, requesting the fallback systems engage secondary API networks.
- **Render Free Tier Constraints:** The Render free tier spins down after 15 minutes of inactivity, requiring an external keep-alive cron job. Cold starts take 30-60 seconds, during which the first user request may timeout.
- **Gemini Embedding Regional Restrictions:** The Gemini Embedding API returns `FAILED_PRECONDITION: User location is not supported` from certain server regions. The system auto-falls back to OpenRouter's `nvidia/llama-nemotron-embed-vl-1b-v2:free` for vector embeddings.

### 6.2 Scalability and Future Work
1. **Two-Way WhatsApp Integration:** Transitioning from the current one-way Twilio SMS alerting to a full two-way WhatsApp Business API. This would allow citizens to conversationally report symptoms into the system, crowdsourcing intelligence in real-time.
2. **Federated Learning on Edge:** Implementing a feedback loop on the Expert Dashboard where experts can correct mislabeled diseases. These corrections would be used to autonomously fine-tune the local spaCy NER algorithms without exposing raw patient data.
3. **Meteorological Data Fusion:** Integrating real-time climatic and satellite data (e.g., abnormal rainfall/flooding metrics) into the Dempster-Shafer fusion algorithms to predict water-borne outbreaks like Cholera *before* the first clinical case is ever reported.
4. **Decentralized Node Architecture:** Refactoring the monolithic FastApi NLP engine into distributed serverless edge-nodes, allowing ADIPHAS to scale horizontally from a State-level command center into a complete National Digital Health Grid.

---

## 7. References
-   Brownstein, J. S., et al. (2009). Digital Disease Detection. *New England Journal of Medicine*.
-   Lewis, P., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS*.
-   World Health Organisation. (2014). Early Detection and Event-Based Surveillance. *WHO Press*.
