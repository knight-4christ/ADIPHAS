# ADIPHAS: Testing & Evaluation Guide

This guide provides a structured protocol for verifying the technical and scientific claims of the ADIPHAS system.

---

## 1. NLP Accuracy Evaluation (Disease & Location)
*How to measure if the bot is extracting data correctly.*

1.  **Login** as an **EXPERT** or **ADMIN**.
2.  Navigate to **System Evaluation** in the sidebar.
3.  Go to the **Manual Annotation** tab.
4.  **Action**: Paste a recent Nigerian health headline (e.g., from *Punch Health* or *NCDC*). 
    *   *Example*: "Lagos Ministry of Health monitors Lassa Fever suspects in Ikorodu."
5.  Click **Run ADIPHAS Extraction**.
6.  Compare the "System Insight" with the text.
7.  **Action**: Scroll down and select the "Ground Truth" (what the system *should* have found).
8.  Click **Submit to Evaluation Engine**.
9.  **Result**: Check the **Performance Metrics** tab to see your cumulative F1-Score, Precision, and Recall update.

---

## 2. Forecast Model Validation (MAE/RMSE)
*How to verify the accuracy of the predictive modeling.*

1.  Navigate to **IDSR Analytics** -> **Predictive Modeling**.
2.  Select an LGA (e.g., **Alimosho**) and a disease (e.g., **Cholera**).
3.  Click **Run Forecast Model**.
4.  **Observation**: Look at the **Model Performance Metrics** section.
    *   The **MAE (Mean Absolute Error)** tells you how many cases the model was off by, on average, during its internal backtest.
    *   A lower MAE relative to the case count indicates a more reliable forecast.
5.  **Visualization**: Verify the "95% Confidence Interval" (red shaded area) on the chart. It indicates the statistical uncertainty of the 4-week prediction.

---

## 3. Knowledge Fusion & Deduplication Test
*How to verify the "Diversity Index" and "De-syndication" logic.*

1.  Navigate to the **Local Health Feed**.
2.  Expand a detailed alert.
3.  **Action**: Look at the **Transparency Trace**.
4.  **Verification**: 
    *   Check for "Deduplicated syndicated report from..." in the trace. (This confirms identical news items weren't double-counted).
    *   Look for the **Scientific Confidence Score**. It should be higher for alerts confirmed by multiple source types (e.g., *NCDC Official* + *Daily News*).

---

## 4. End-to-End Alerting Test
*How to verify the citizen-facing notification path.*

1.  Ensure you have a **User Profile** with an LGA set (e.g., **Ikeja**).
2.  **Action**: Run the scraper or manually ingest an alert matching your LGA via the API/Database.
3.  **Verification**:
    *   Check the sidebar. You should see a **notification badge** (red number) next to **Personal Alerts**.
    *   Navigate to **Personal Alerts** and verify the alert matches your location.

---

## 5. Technical Stress Test
*How to verify system resilience.*

1.  **Simulation**: Stop the backend server and try to navigate the UI.
2.  **Observation**: The UI should display a "Connection Error" toast rather than crashing entirely.
3.  **Startup**: Run `python run_backend.py` and verify all agents (Scouts, Analysts, Predictors) initialize without `AttributeError`.
