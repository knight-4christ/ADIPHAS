<div align="center">
  <img src="docs/assets/banner.png" alt="ADIPHAS Banner" width="100%">
  
  # ADIPHAS
  ### Autonomous Disease Intelligence & Personal Health Advisory System
  
  [![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-v0.109-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
  [![Streamlit](https://img.shields.io/badge/Streamlit-v1.30%2B-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
  [![Live](https://img.shields.io/badge/Live-adiphas.streamlit.app-00C9A7)](https://adiphas.streamlit.app)
  [![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE.txt)
</div>

---

## 🚀 Overview

ADIPHAS is a state-of-the-art **Hybrid Intelligence System** designed for autonomous epidemiological surveillance and personalized health risk mitigation. By bridging the gap between formal health reports (IDSR) and informal news signals (EBS), ADIPHAS provides a robust, research-grade early warning shield for urban health governance in Nigeria.

The system leverages **Dempster-Shafer Theory of Evidence** to combine conflicting signals from independent sources, ensuring highly reliable outbreak detection even in noisy environments.

---

## ✨ Key Features

- **📡 Autonomous Scout (EBS)**: Real-time news scraping and NLP entity extraction using `spaCy` and **Gemini 2.5 Flash**.
- **🧠 Knowledge Fusion**: Mathematical reconciliation of multi-source signals using the **Dempster-Shafer Framework**.
- **📩 Proactive Intelligence Delivery**: Automatically synthesizes and emails tailored situational briefings (Community vs. Expert) every 2 hours using a background multithreaded dispatcher.
- **🔒 Secure Access & Verification**: Hardened user authentication featuring cryptographic email validation and secure "Forgot Password" recovery flows.
- **📍 Hyper-Local Analytics**: Browser-native HTML5 Geolocation instantly anchors users to their exact Local Government Area (LGA) for tailored outbreak alerts.
- **🛡️ Advisory Engine**: A Hybrid clinical assistant backed by an OpenRouter Tiered Model Rotation (exponential rate-limit backoff).
- **⚡ Micro-Frontend Architecture**: Fully modularized dashboard leveraging lazy-loading (`@st.fragment`) to ensure instant page-shell rendering even under heavy AI computation.

---

## 🏗 System Architecture

```mermaid
graph TD
    A[Public News/NCDC Portal] -->|Scraper Agent| B(EBS Intelligence)
    B -->|NLP Processor| C{Knowledge Fusion}
    D[Official IDSR CSVs] -->|Ingestion Agent| E(Historical Data)
    C -->|Dempster-Shafer| F[Verified Alerts]
    E -->|Statistical Anomaly| G[Predictive Forecasts]
    F --> H[Streamlit Dashboard]
    G --> H
    I[User Health Profile] -->|Genotype/Location| J[Risk Scoring Engine]
    J --> H
```

---

## 🛠 Installation & Setup

### 🌐 Live Production Instance
ADIPHAS is deployed and accessible at:
- **Frontend:** [adiphas.streamlit.app](https://adiphas.streamlit.app)
- **Backend API:** [adiphas.onrender.com](https://adiphas.onrender.com/healthcheck)

### 🚀 Quick Start (Local Development)
The easiest way to run the entire hybrid system (Backend, Frontend, and Autonomous Agents) locally:

1. **Clone & Configure**:
   ```bash
   git clone https://github.com/your-repo/ADIPHAS.git
   cd ADIPHAS
   ```
2. **Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   GEMINI_API_KEY=your_gemini_key
   TAVILY_API_KEY=your_tavily_key
   ```
3. **Seed Real Epidemic Data**:
   Ensure the Predictive Agent operates on verified, real-world data (Cholera/Lassa):
   ```python
   python seed_real_data.py
   ```
4. **Boot the Analytics Engine**:
   Instantly deploy the FastAPI backend, Streamlit UI, and Background Schedulers. This script automatically handles cold-start delays and port conflicts:
   
   **For Windows (PowerShell):**
   ```powershell
   .\start_adiphas.ps1
   ```
   
   **For Linux / macOS:**
   ```bash
   chmod +x start_adiphas.sh
   ./start_adiphas.sh
   ```

---

## 🔬 Project Defense & Live Simulation

ADIPHAS includes dedicated scripts to demonstrate its capabilities during live defenses:

1. **Verify Automated Delivery Capabilities**:
   - Register a new account and instantly receive a verification email. Once verified, observe how the system actively emails you tailored health summaries every 2 hours.
2. **Observe Autonomous Cycles**:
   - Watch the terminal running `start_adiphas.ps1` to see the Orchestrator, Scraper, and NLP processor actively categorizing new intelligence globally.
3. **Test the LLM Fallback Engine**:
   - ADIPHAS features a proprietary robust fallback mechanism (`model_config.py`). If the primary Gemini model is rate-limited, it automatically swerves through a chain of **25 free OpenRouter models** to keep the system alive without crashing.

---

## ⚠️ Important Considerations for Production

- **Database:** ADIPHAS uses **Neon PostgreSQL** in production. For local development, it falls back to SQLite automatically if `DATABASE_URL` is not set.
- **Authentication:** Password hashing uses native `bcrypt` (not `passlib`). The `SECRET_KEY` environment variable is mandatory.
- **AI Budget:** The scheduler runs every 2 hours to stay within free-tier API limits. Add OpenRouter credits ($5-10) for higher frequency.
- **Keep-Alive:** Render free tier requires a cron job pinging `/healthcheck` every 5 minutes.
- **Full deployment details:** See **[Deployment Guide](./DEPLOYMENT_GUIDE.md)**.

---

## 📜 Documentation

- 📓 **[Methodology](./METHODOLOGY.md)**: Mathematical proof of the Dempster-Shafer Fusion Logic.
- 🚀 **[Deployment Guide](./DEPLOYMENT_GUIDE.md)**: Comprehensive guide for cloud & local hosting.
- 🧪 **[Testing Guide](./TESTING_GUIDE.md)**: Audit trail and validation procedures.

---

<div align="center">
  Developed for Public Health Intelligence & Urban Governance.
</div>
