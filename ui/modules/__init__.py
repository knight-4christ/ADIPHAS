import streamlit as st
from datetime import datetime, timezone, timedelta

# --- West Africa Time (WAT = UTC+1) ---
# All user-facing timestamps in the UI should use this timezone.
# Backend/DB operations remain in UTC for consistency.
WAT = timezone(timedelta(hours=1))

def now_wat() -> datetime:
    """Returns the current datetime in West Africa Time (UTC+1)."""
    return datetime.now(WAT)

def to_wat(dt: datetime) -> datetime:
    """Converts a naive (assumed UTC) or aware datetime to WAT."""
    if dt.tzinfo is None:
        # Treat naive datetimes as UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(WAT)

def render_footer():
    """Renders the mandatory medical disclaimer footer."""
    footer_color = "#94a3b8"
    
    st.markdown(
        f"""
        <div style='text-align: center; color: {footer_color}; font-size: 0.8rem; padding: 20px 0;'>
            <p><strong>⚠️ ADIPHAS Critical Enforcement Disclaimer</strong></p>
            <p>ADIPHAS is an advisory support tool and does not provide medical diagnoses. 
            Consult a clinician for professional evaluation.</p>
        </div>
        """, 
        unsafe_allow_html=True
    )

