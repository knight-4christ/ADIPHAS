from sqlalchemy import Column, Integer, String, Date, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String, unique=True, index=True)
    full_name = Column(String)
    age = Column(Integer)
    gender = Column(String)
    state = Column(String)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="CITIZEN") # CITIZEN or EXPERT
    
    # Biodata / Health Profile
    blood_group = Column(String, nullable=True)
    genotype = Column(String, nullable=True)
    health_conditions = Column(Text, nullable=True)
    location_lga = Column(String, nullable=True)
    
    # Gamification
    impact_score = Column(Integer, default=0)
    contributions = Column(Integer, default=0) # Number of symptoms reported
    
    created_at = Column(DateTime, default=datetime.utcnow)

class IDSRRecord(Base):
    __tablename__ = "idsr_records"

    id = Column(Integer, primary_key=True, index=True)
    facility_id = Column(String)
    lga_code = Column(String)
    state_code = Column(String)
    disease = Column(String)
    week_start = Column(Date)
    cases = Column(Integer)
    deaths = Column(Integer)
    reporting_week = Column(Integer)
    reporters_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class EBSAlert(Base):
    __tablename__ = "ebs_alerts"

    alert_id = Column(String, primary_key=True, default=generate_uuid)
    source = Column(String)
    url = Column(String, unique=True, index=True, nullable=True)
    text = Column(Text)
    timestamp = Column(DateTime)
    location_text = Column(String)
    disease = Column(String, nullable=True)
    location_lat = Column(Float, nullable=True)
    location_lon = Column(Float, nullable=True)
    collected_by = Column(String)
    verified = Column(Boolean, default=False)
    risk_level = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    ai_powered = Column(Boolean, default=False)
    policy_alert = Column(Boolean, default=False)
    requires_hitl = Column(Boolean, default=False)
    is_vectorized = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class SystemActivity(Base):
    __tablename__ = "system_activities"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    agent = Column(String, index=True)
    message = Column(Text)

class EvaluationSample(Base):
    __tablename__ = "evaluation_samples"

    id = Column(Integer, primary_key=True, index=True)
    raw_text = Column(Text)
    expected_entities = Column(Text) # JSON string of {"diseases": [], "locations": []}
    actual_entities = Column(Text)   # JSON string of {"diseases": [], "locations": []}
    f1_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
