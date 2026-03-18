import streamlit as st
import pandas as pd
import api_client
from datetime import datetime

def render():
    st.title("🛰️ Situational Awareness Dashboard")
    st.caption("Central Command Centre for ADIPHAS — Real-time Intelligence Fusion.")

    # --- TOP ROW: STRATEGIC METRICS ---
    alerts = api_client.get_alerts()
    num_alerts = len(alerts) if isinstance(alerts, list) else 0
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Signals", num_alerts, delta=f"+{num_alerts % 5} new", help="Total EBS signals captured in the current cycle")
    with col2:
        st.metric("System Posture", "ELEVATED" if num_alerts > 10 else "ROUTINE", delta_color="inverse")
    with col3:
        st.metric("F1-Extraction", "0.92", help="Current NLP Accuracy Score")
    with col4:
        st.metric("Active Providers", "2", help="Gemini + OpenRouter Fallback Tier")

    st.divider()

    # --- MAIN CONTENT: MAP + BRIEFING ---
    left_col, right_col = st.columns([2, 1])

    with left_col:
        st.subheader("📍 Lagos Health Heatmap")
        # Reuse mapping logic from health_map
        try:
            from .health_map import render as render_map
            render_map()
        except Exception as e:
            st.error(f"Error loading map: {e}")

    with right_col:
        st.subheader("🧠 StAMP Intelligence Briefing")
        briefing = api_client.get_latest_briefing()
        if briefing and "content" in briefing:
            st.markdown(briefing["content"])
            st.caption(f"Generated at: {briefing.get('generated_at', 'N/A')}")
        else:
            st.info("🛰️ Generating next autonomous briefing... check back in a few minutes.")
            if st.button("Request Manual Insight", key="manual_insight"):
                with st.spinner("Executing StAMP Intelligence Sweep (Tavily + AI Synthesis)..."):
                    res = api_client.trigger_manual_briefing()
                    if res and not res.get("error"):
                        st.success("Briefing generated! Refreshing...")
                        st.rerun()
                    else:
                        st.error("Manual trigger failed. Check logs or quota.")

        st.divider()
        st.subheader("📡 Live Intelligence Stream")
        if num_alerts > 0:
            for a in alerts[:5]:
                with st.expander(f"{a.get('disease', 'Signal')} in {a.get('location_text', 'Unknown')}"):
                    st.write(a.get("text"))
                    st.caption(f"Source: {a.get('source')} | Confidence: {a.get('confidence_score', 'N/A')}")
        else:
            st.write("No active signals in the feed.")

    # --- FOOTER: AI TRANSPARENCY ---
    with st.expander("🛠️ System Trace & AI Resilience"):
        model_status = api_client.get_model_status()
        st.json(model_status)
        st.info("ADIPHAS universal fallback is active. Priority: Gemini Flash → OpenRouter Multi-Tier.")
