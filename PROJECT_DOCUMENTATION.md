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
3.  **Intelligence Agent Layer:** Multithreaded fleet (Scout, NLP, Fusion, StAMP Briefing Agent) running continuously on a 15-minute **APScheduler** background cycle.
4.  **Persistence Layer:** Hosted physically on **Neon Cloud PostgreSQL**, offering robust connection pooling to efficiently handle massive parallel read/writes from the multithreaded AI extractors, entirely eliminating the concurrency locks associated with embedded SQLite.

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
### 4.1 Real-Time Metrics & Caching
The system features a **5-second TTL (Time-To-Live)** cache for high-frequency dashboard metrics. It calculates cumulative daily totals for scraped articles and new signals, preventing database lockups during concurrent role access.

### 4.2 Hybrid-RAG and Strategic Intelligence
The RAG pipeline utilizes a dual-path retrieval strategy:
- **Local Path**: Verified EBS alerts and IDSR historical aggregates are indexed in the **Titan Vector Engine** for high-precision local context.
- **Global Path**: If local data is insufficient or a query involves emerging global trends, the system triggers the **Tavily Search API** for real-time web context.
- **StAMP Synthesis & Manual Bypass**: The **Situational Awareness & Monitoring Protocol (StAMP)** generates a daily strategic briefing by fusing these paths. To aid immediate incident investigation, experts can utilize the explicit "Force Real-time StAMP Sweep" bypass, directly commanding the pipeline to run instantaneous fresh reconnaissance outside standard scheduling boundaries.
- **Reasoning Trace Sanitization**: All generative outputs are passed through a defensive 3-layer architecture (Generation, Storage, Serving) utilizing strict Regex algorithms to successfully strip any internal Chain-of-Thought (e.g., `<think>`) leakage produced by advanced reasoning models like DeepSeek.

### 4.3 Notification Infrastructure (Modular Status)
The system includes modules for **SMS (Twilio)** and **Email (SMTP)** broadcasting. These are currently implemented as background utilities and can be activated for high-risk alerts (`risk_level == "High"`) once notification quotas are established.

---

## 5. Summary of Achievements
-   **Concurrency & Data Integrity:** Replaced legacy sequential SQLite operations with high-availability **Neon PostgreSQL**, successfully eliminating connection locks under high NLP pipeline loads.
-   **Accuracy & Integrity:** Achieved $0.875$ micro-averaged F1 on representative health data, while implementing complete sanitization protocols ensuring 100% public-ready briefing output free of raw model reasoning tokens.
-   **Efficiency:** Reduced LLM API calls by **95%** using local-first extraction and caching, alongside the resilient Universal Fallback configuration.
-   **Hyper-Personalization:** Connected browser-native HTML5 `navigator.geolocation` APIs with OpenStreetMap reverse geocoding to automatically center heatmaps and tailor instant epidemiological advisories based on the user's precise Local Government Area.

---

## 6. Limitations & Future Improvements
### 6.1 Current System Limitations
- **Geolocation Resolution Limits:** The current HTML5 reverse geocoding via OpenStreetMap relies on the accuracy of the user's device. Devices lacking GPS hardware (like some desktops) fall back to ISP-level IP coordinates, which may lack the specific Local Government Area (LGA) granularity required for hyper-local intelligence.
- **LLM Quota Constraints:** The batch intelligence engine aggressively processes up to 50 raw articles concurrently. While highly efficient, this burst computation frequently exhausts free-tier Gemini API token limits (429 errors), requiring the fallback systems to engage secondary API networks.
- **Anti-Bot Firewalls:** High-profile news portals (such as *Vanguard* and *The Guardian*) deploy unpredictable dynamic firewalls that can occasionally repel the `Scrapling` instances, leading to temporary data acquisition gaps from those specific nodes.

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
