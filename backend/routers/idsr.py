from fastapi import APIRouter, Depends, UploadFile, File  # type: ignore[import-untyped]
from sqlalchemy.orm import Session  # type: ignore[import-untyped]
from datetime import datetime
from typing import Optional

from backend import models, schemas  # type: ignore[import-untyped]
from backend.database import get_db  # type: ignore[import-untyped]
from backend.dependencies import ingestion_agent, alerting_engine  # type: ignore[import-untyped]

router = APIRouter(tags=["IDSR Management"])

@router.post("/api/data/idsr_upload")
def upload_idsr(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = file.file.read()
    result = ingestion_agent.process_idsr_csv(content, db)
    return result

@router.get("/api/data/idsr_history")
def get_idsr_history(lga_code: Optional[str] = None, disease: Optional[str] = None, db: Session = Depends(get_db)):
    """Returns raw IDSR weekly records for a given LGA and disease for chart rendering."""
    query = db.query(models.IDSRRecord)
    if lga_code:
        query = query.filter(models.IDSRRecord.lga_code == lga_code)
    if disease:
        query = query.filter(models.IDSRRecord.disease == disease)
    records = query.order_by(models.IDSRRecord.week_start).all()
    return [
        {
            "week_start": str(r.week_start),
            "cases": r.cases,
            "deaths": r.deaths,
            "lga_code": r.lga_code,
            "disease": r.disease,
            "reporting_week": r.reporting_week
        }
        for r in records
    ]

@router.post("/api/data/forecast", response_model=schemas.PredictionReport)
def predict_forecast(request: schemas.PredictionRequest, db: Session = Depends(get_db)):
    # --- Real Data Strategy ---
    # 1. Try IDSR records (structured weekly case counts)
    records = (
        db.query(models.IDSRRecord)
        .filter(
            models.IDSRRecord.lga_code == request.lga_code,
            models.IDSRRecord.disease == request.disease
        )
        .order_by(models.IDSRRecord.week_start)
        .all()
    )
    historical_data = [r.cases for r in records] if len(records) >= 4 else None

    # 2. Fallback: count EBSAlerts per week (real scraped intelligence)
    if not historical_data:
        from sqlalchemy import func, extract  # type: ignore[import-untyped]
        weekly_counts = (
            db.query(
                func.strftime('%Y-%W', models.EBSAlert.timestamp).label('week'),
                func.count(models.EBSAlert.alert_id).label('count')
            )
            .filter(
                models.EBSAlert.disease == request.disease,
                models.EBSAlert.location_text.ilike(f"%{request.lga_code}%")
            )
            .group_by(func.strftime('%Y-%W', models.EBSAlert.timestamp))
            .order_by(func.strftime('%Y-%W', models.EBSAlert.timestamp))
            .all()
        )
        if len(weekly_counts) >= 4:
            historical_data = [wc.count for wc in weekly_counts]

    forecast, trace = alerting_engine.forecast_cases(
        request.lga_code, request.disease, historical_data=historical_data
    )

    # Handle "insufficient data" gracefully
    if forecast.get("insufficient_data"):
        return {
            "lga_code": request.lga_code,
            "disease": request.disease,
            "week_start": datetime.now().date(),
            "pred_cases": 0, "pred_ci_lower": 0, "pred_ci_upper": 0,
            "anomaly_flag": False,
            "forecast": [], "ci_lower": [], "ci_upper": [],
            "mae": 0.0, "rmse": 0.0,
            "validation_period": "N/A",
            "policy_recommendation_plan": forecast.get("message"),
            "trace": trace
        }

    # Run anomaly detection with real data
    is_anom, _ = alerting_engine.detect_anomalies(request.lga_code, request.disease, historical_data)

    return {
        "lga_code": request.lga_code,
        "disease": request.disease,
        "week_start": datetime.now().date(),
        "pred_cases": forecast["forecast"][0],
        "pred_ci_lower": forecast["ci_lower"][0],
        "pred_ci_upper": forecast["ci_upper"][0],
        "anomaly_flag": is_anom,
        # Extra fields consumed by UI
        "forecast": forecast["forecast"],
        "ci_lower": forecast["ci_lower"],
        "ci_upper": forecast["ci_upper"],
        "mae": forecast["mae"],
        "rmse": forecast["rmse"],
        "validation_period": forecast.get("validation_period", "2 weeks"),
        "policy_recommendation_plan": forecast.get("policy_recommendation_plan"),
        "data_points_used": forecast.get("data_points_used", 0),
        "trace": trace
    }
