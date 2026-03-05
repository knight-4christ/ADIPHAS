from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime

class IDSRRecordCreate(BaseModel):
    facility_id: str
    lga_code: str
    state_code: str
    disease: str
    week_start: date
    cases: int
    deaths: int
    reporting_week: int
    reporters_notes: Optional[str] = None

class EBSAlertCreate(BaseModel):
    source: str
    text: str
    timestamp: datetime
    location_text: str
    disease: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    collected_by: str
    summary: Optional[str] = None
    ai_powered: Optional[bool] = False
    policy_alert: Optional[bool] = False
    requires_hitl: Optional[bool] = False

class EBSAlertResponse(EBSAlertCreate):
    alert_id: str
    verified: bool
    risk_level: Optional[str] = None
    created_at: datetime

    model_config = {
        "from_attributes": True
    }

class SymptomPayload(BaseModel):
    user_id: str
    timestamp: datetime
    symptoms: List[str]
    duration_days: int
    exposures: Optional[str] = None
    travel_history: Optional[str] = None

class PHASNote(BaseModel):
    user_id: str
    date: date
    risk_score: float
    risk_category: Optional[str] = "Low"
    ai_situational_summary: Optional[str] = None
    ai_clinical_insight: Optional[str] = None
    suggestions: List[str]
    tracking_plan: List[str]
    trace: Optional[List[dict]] = None

class PredictionRequest(BaseModel):
    lga_code: str
    disease: str
    lookahead_weeks: int

class PredictionReport(BaseModel):
    lga_code: str
    disease: str
    week_start: date
    pred_cases: Optional[int] = None
    pred_ci_lower: Optional[int] = None
    pred_ci_upper: Optional[int] = None
    forecast: Optional[List[float]] = None
    ci_lower: Optional[List[float]] = None
    ci_upper: Optional[List[float]] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    validation_period: Optional[str] = None
    epidemiological_narrative: Optional[str] = None
    policy_recommendation_plan: Optional[str] = None
    anomaly_flag: bool = False
    data_points_used: Optional[int] = None
    trace: Optional[List[dict]] = None

# --- Authentication Schemas ---

class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str = "CITIZEN"
    blood_group: Optional[str] = None
    genotype: Optional[str] = None
    health_conditions: Optional[str] = None
    location_lga: Optional[str] = None
    impact_score: int = 0
    contributions: int = 0

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserOut(UserBase):
    id: str
    created_at: datetime

    model_config = {
        "from_attributes": True
    }

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    id: Optional[str] = None

class EvaluationSampleCreate(BaseModel):
    raw_text: str
    expected_entities: str # JSON string
    actual_entities: str   # JSON string
    f1_score: Optional[float] = None

class EvaluationSampleOut(EvaluationSampleCreate):
    id: int
    created_at: datetime

    model_config = {
        "from_attributes": True
    }
