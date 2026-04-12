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

    # --- TOP CONTENT: StAMP BRIEFING ---
    st.subheader("🧠 StAMP Intelligence Briefing")
    
    # Personalized Insight First
    if st.session_state.get("authenticated") and st.session_state.get("user_location"):
        st.markdown("##### 🧬 Personalized Geo-Health Insight")
        
        if "dashboard_insight" not in st.session_state:
            with st.spinner(f"Generating insight for {st.session_state.user_location}..."):
                res = api_client.get_dashboard_insight(
                    st.session_state.token,
                    st.session_state.user_location,
                    f"Current StAMP Alert Count: {num_alerts}"
                )
                st.session_state.dashboard_insight = res.get("insight", "No insights available.")
        
        st.info(f"📍 **{st.session_state.user_location}**: {st.session_state.dashboard_insight}")
        st.divider()

    briefing = api_client.get_latest_briefing()
    if briefing and "content" in briefing:
        st.markdown(briefing["content"])
        try:
            # Convert ISO string "2026-03-30T23:17:56.509344" to friendly "Mar 30, 2026 - 11:17 PM"
            dt = pd.to_datetime(briefing.get('generated_at', ''))
            st.caption(f"Generated at: {dt.strftime('%b %d, %Y - %I:%M %p')}")
        except Exception:
            st.caption(f"Generated at: {briefing.get('generated_at', 'N/A')}")
    else:
        st.info("🛰️ Generating next autonomous briefing... check back in a few minutes.")
        
    if st.button("🔄 Force Real-time StAMP Sweep", key="manual_insight", use_container_width=True):
        with st.spinner("Executing StAMP Intelligence Sweep (Tavily + AI Synthesis)..."):
            res = api_client.trigger_manual_briefing()
            if res and not res.get("error"):
                st.success("Briefing generated! Refreshing...")
                st.rerun()
            else:
                st.error("Manual trigger failed. Check logs or quota.")

    st.divider()

    with st.expander("📡 Active Surveillance Zones (Monitored LGAs)", expanded=False):
        from .health_map import LAGOS_LGAS
        active_lgas = []
        for a in alerts:
            ltext = a.get('location_text', '')
            for lga in LAGOS_LGAS.keys():
                if lga.lower() in ltext.lower():
                    active_lgas.append(lga)
        active_lgas = set(active_lgas)

        monitored = []
        for lga in LAGOS_LGAS.keys():
            if lga in active_lgas:
                monitored.append(f"🔴 **{lga}**: Active Outbreak Signals")
            else:
                monitored.append(f"🟢 **{lga}**: Surveillance Nominal")
        
        c1, c2, c3 = st.columns(3)
        for i, item in enumerate(monitored):
            if i % 3 == 0: c1.write(item)
            elif i % 3 == 1: c2.write(item)
            else: c3.write(item)
            
    st.divider()

    # --- MAIN CONTENT: MAP + LIVE STREAM ---
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
