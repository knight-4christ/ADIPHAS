# ADIPHAS: Scientific & Technical Methodology

## 1. Dempster-Shafer Knowledge Fusion Framework

The ADIPHAS Fusion Layer (Synthesizers) implements **Dempster-Shafer (DS) Theory of Evidence** to combine conflicting signals from independent acquisition sources.

### 1.1 Basic Probability Assignment (BPA)
Each source $S_i$ is treated as a sensor with a reliability weight $w_i \in [0.3, 0.95]$. We define two masses:
1. $m_i(Real) = w_i$: The mass of evidence that the outbreak is a true signal.
2. $m_i(U) = 1 - w_i$: The mass of uncertainty assigned to the universal set (Unknown).

### 1.2 Combined Belief Calculation
Using a recursive version of Dempster's rule for pooling independent evidence across $n$ unique sources:

$$m_{final}(Real) = 1 - \prod_{i=1}^{n} (1 - w_i)$$

### 1.3 Comparative Analysis: Shift to DST
Moving from a weighted average to Dempster-Shafer (DS) Theory provides several advantages and considerations for public health intelligence:

**Pros:**
- **Explicit Ignorance Modelling**: Unlike traditional probability, DS distinguishes between "lack of evidence" and "evidence of non-occurrence." In early outbreak detection, "we don't know" is a more honest state than "0% probability."
- **Asymptotic Convergence**: As independent reports increase, the combined belief rises sharply (e.g., three sources with 0.6 weight yield 0.936 belief). This mirrors how epidemiological "triangulation" works in the field.
- **Robustness to Outliers**: A single low-reliability source cannot "pull down" the belief of several high-reliability sources as easily as in a standard average.

**Cons/Considerations:**
- **Independence Assumption**: DS assumes sources are independent. If multiple news sites copy the same agency report (syndication), the math may over-estimate certainty. ADIPHAS mitigates this via **MD5 Content Hashing** to ensure only unique reports are combined.
- **Conflict Handling**: If two highly reliable sources provide totally contradictory reports, DS calculation can become unstable (Zadeh's Paradox). The system handles this by grouping signals by Disease-Location keys before fusion.

*Significance*: This approach mathematically reflects that as more independent sources corroborate a signal, the overall belief asymptotically approaches 1.0, even if individual sources aren't perfectly reliable. It naturally handles source diversity without arbitrary bonuses.

---

## 2. NLP Evaluation Protocol

To ensure research-grade accuracy, ADIPHAS implements a continuous evaluation framework for its Named Entity Recognition (NER) agents.

### 2.1 Extraction Targets
- **Diseases**: 6 categories (Cholera, Lassa Fever, etc.) using hybrid spaCy NER + RegEx.
- **Geography**: 20 Lagos LGAs via strict gazetteer alignment.
- **Temporal**: ISO-8601 normalization via `python-dateutil`.

### 2.2 Metrics Calculation
The "Evaluation Engine" (Phase 16) computes Precision ($P$), Recall ($R$), and F1-score ($F1$) against manual expert annotations ($A$):

$$F1 = 2 \times \frac{P \times R}{P + R}$$

*Benchmark*: High-rigor prototypes target $F1 > 0.85$ for disease detection.

---

## 3. Forecasting & Epidemic Modeling

### 3.1 Predictive Logic
ADIPHAS uses a **Weighted Moving Average + Linear Trend** model for short-term (4-week) forecasting.

### 3.2 Accuracy Validation (Backtesting)
Before generating a future forecast, the engine performs an **Internal Backtest** on the last 2 weeks of available data.

**Error Metrics**:
1. **MAE (Mean Absolute Error)**: $\frac{1}{n} \sum |y_i - \hat{y}_i|$
2. **RMSE (Root Mean Square Error)**: $\sqrt{\frac{1}{n} \sum (y_i - \hat{y}_i)^2}$

*Transparency*: Every forecast shown in the UI is accompanied by its MAE, allowing public health officials to gauge the reliability of the prediction.

---

## 4. StAMP Intelligence Protocol
**Situational Awareness & Monitoring Protocol (StAMP)** is the ADIPHAS autonomous intelligence engine. It operates on a 24-hour cycle (with 6-hour real-time sweeps) to synthesize a "Strategic Briefing" for health officials.

### 4.1 Real-Time Intelligence (Web Scouting)
The system uses the **Tavily Search API** to pull live epidemiological signals from news sites, social media mentions, and community reports. These are normalized into "Intelligence Snapshots" and stored in the vector store.

### 4.2 Autonomous Synthesis
Every 24 hours, a specialized **Briefing Agent** performs a "Triple-Fusion":
1. **DB Signals**: Verified EBS alerts from the last 7 days.
2. **Anomalies**: NLP-detected outliers in case reports.
3. **Web Context**: Live Tavily news results.

The output is a Markdown-formatted **StAMP Strategic Briefing**, which is delivered to the Governance Dashboard.

---

## 5. Multi-LLM Resilience & High Availability
To prevent intelligence blindness during API outages (e.g., Google Gemini quota limits), ADIPHAS implements a **Universal Fallback Tier**.

### 5.1 Fallback Orchestration
- **Primary Tier**: Google Gemini (Flash/Pro) for cost-efficient reasoning.
- **Secondary Tier (Emergency)**: OpenRouter (Claude/Stepfun/Hunter) for guaranteed availability.
- **Trigger**: Automatic failover occurs upon `429 (Resource Exhausted)` or `500 (Server Error)` from the primary provider.

*Significance*: This ensures that the Advisory Chat and StAMP cycles remain operational even during global LLM outages, maintaining critical public health "eyes-on-target" status.

---

## 6. Personalization & Bio-Aware Advisory (Rule 10 Alignment)
Aligning with the core mission of "tailored insights," the advisory engine injects **User Biodata** directly into the AI prompt:
- **Genotype Sensitivity**: Automatic warnings for Malaria complications in sickle-cell (SS/SC) carriers.
- **Blood Group Logic**: Risk escalation for Cholera in individuals with Blood Group O.
- **Health Conditions**: Chronic respiratory conditions (e.g., Asthma) trigger higher severity ratings during air-quality or flu outbreaks.

---

## 7. Deduplication & Anti-Syndication
To prevent "Echo Chamber" signals (where one news release is syndicated across 50 sites), ADIPHAS applies **MD5 Content Hashing**:
- Normalized Text Hash = `MD5(lower(trim(records)))`
- Fused signals only include content with unique hashes within a 7-day window.
