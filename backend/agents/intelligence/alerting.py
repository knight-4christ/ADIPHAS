import numpy as np
import math
from datetime import datetime

class AlertingEngine:
    """
    Engine responsible for detecting anomalies and forecasting disease cases.
    Incorporates error metrics (MAE, RMSE) for academic rigor.
    """
    def __init__(self, gemini_model=None):
        self.gemini_model = gemini_model
    
    def generate_narrative(self, lga_code, disease, forecast_data, is_anomaly):
        """Uses Gemini to orchestrate the policy plan based on hard statistical thresholds."""
        if not self.gemini_model: return None
        
        prompt = f"""
        Act as the Chief Public Health Orchestrator for Lagos State, Nigeria.
        
        Underlying Mathematical Models Output:
        - Target: {disease} in {lga_code}
        - 4-week WMA Forecast Cases: {forecast_data['forecast']}
        - Forecast Error (MAE): {forecast_data['mae']}
        - Z-Score Anomaly Triggered: {is_anomaly}
        
        Your task is to orchestrate a high-level `policy_recommendation_plan`.
        Because this is a Hybrid AI system, you MUST respect the math: if an anomaly is triggered, your policy must reflect an emergency posture. If the forecast is flat and no anomaly is triggered, maintain a routine surveillance posture. 
        
        Provide:
        1. A concise (1 sentence) epidemiological interpretation of the math.
        2. A clear Public Health Preparedness Action Plan.
        """
        try:
            from backend.core.model_config import smart_generate
            text, model_used = smart_generate(self.gemini_model, prompt, context="ForecastNarrative")
            return text or "Narrative generation currently unavailable."
        except:
            return "Narrative generation currently unavailable."

    def _calculate_metrics(self, actual, predicted):
        """Calculates MAE and RMSE for the given sets."""
        if not actual or not predicted or len(actual) != len(predicted):
            return 0.0, 0.0
        
        actual = np.array(actual)
        predicted = np.array(predicted)
        
        mae = np.mean(np.abs(actual - predicted))
        rmse = math.sqrt(np.mean((actual - predicted)**2))
        
        return round(float(mae), 4), round(float(rmse), 4)

    def detect_anomalies(self, lga_code, disease, historical_counts=None):
        """
        Z-score anomaly detection. A data point is anomalous when it
        exceeds mean + 2 * std_dev of the historical baseline.
        Requires at least 4 real data points; returns False with an
        'insufficient data' trace when unavailable.
        """
        trace = []
        trace.append({"step": f"Anomaly detection: {disease} in {lga_code}",
                       "timestamp": datetime.now().replace(microsecond=0)})

        if not historical_counts or len(historical_counts) < 4:
            trace.append({"step": "Insufficient historical data for anomaly detection (need ≥4 data points).",
                           "timestamp": datetime.now().replace(microsecond=0)})
            return False, trace

        baseline = np.array(historical_counts[:-1], dtype=float)
        latest = float(historical_counts[-1])

        mean = np.mean(baseline)
        std = np.std(baseline)

        if std == 0:
            result = False
            z_score = 0.0
        else:
            z_score = (latest - mean) / std
            result = bool(z_score > 2.0)

        trace.append({"step": f"Z-score: {z_score:.2f} (mean={mean:.1f}, std={std:.1f}, latest={latest})",
                       "timestamp": datetime.now().replace(microsecond=0)})
        trace.append({"step": f"Result: {'ANOMALY DETECTED' if result else 'No anomaly'}",
                       "timestamp": datetime.now().replace(microsecond=0)})

        return result, trace
    
    def forecast_cases(self, lga_code, disease, historical_data=None, weeks=4):
        """
        Forecast future cases using a hybrid (Math + AI) approach.
        Requires at least 4 real data points. Returns an 'insufficient data'
        response when historical records are unavailable.
        """
        trace = []
        trace.append({"step": f"Initializing Forecasting Engine for {disease} in {lga_code}...", "timestamp": datetime.now().replace(microsecond=0)})
        
        # Require real data — no synthetic fallbacks
        if not historical_data or len(historical_data) < 4:
            trace.append({"step": f"Insufficient data: Only {len(historical_data) if historical_data else 0} data points available (need ≥4).", "timestamp": datetime.now().replace(microsecond=0)})
            return {
                "forecast": [], "ci_lower": [], "ci_upper": [],
                "mae": 0.0, "rmse": 0.0, "validation_period": "N/A",
                "insufficient_data": True,
                "message": f"Insufficient historical data for {disease} in {lga_code}. Need at least 4 weekly records to generate a forecast. The system is actively collecting real-time intelligence — forecasts will become available as more data accumulates."
            }, trace
        
        # 1. CORE SKELETON (WMA + Trend Math) — using REAL data only
        train = historical_data[:-2]; test = historical_data[-2:]
        val_pred = [sum(train)/len(train)] * 2
        mae, rmse = self._calculate_metrics(test, val_pred)
        
        last_3 = historical_data[-3:]; weights = [0.2, 0.3, 0.5]
        base_pred = sum(w * d for w, d in zip(weights, last_3))
        trend = historical_data[-1] - historical_data[-2]
        
        forecast = []
        for i in range(1, weeks + 1):
            p = base_pred + (trend * i * 0.5)
            forecast.append(max(0, round(p)))

        forecast_data = {
            "forecast": forecast,
            "ci_lower": [max(0, round(f - rmse)) for f in forecast],
            "ci_upper": [round(f + rmse) for f in forecast],
            "mae": mae, "rmse": rmse, "validation_period": "2 weeks",
            "data_points_used": len(historical_data)
        }

        # 2. AI ORCHESTRATION — on-demand only (called by user-facing endpoint)
        if self.gemini_model:
            is_anom, _ = self.detect_anomalies(lga_code, disease, historical_data)
            narrative = self.generate_narrative(lga_code, disease, forecast_data, is_anom)
            if narrative:
                forecast_data["policy_recommendation_plan"] = narrative
                trace.append({"step": "Hybrid Orchestration: AI finalized policy plan based on statistical thresholds.", "timestamp": datetime.now().replace(microsecond=0)})
        
        trace.append({"step": "Forecasting cycle complete.", "timestamp": datetime.now().replace(microsecond=0)})
        return forecast_data, trace
