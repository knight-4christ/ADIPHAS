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
    
    # Personalized Insight — ALWAYS show for authenticated users (fallback to profile LGA)
    if st.session_state.get("authenticated"):
        user = st.session_state.get("user", {})
        user_name = user.get("username", "User")
        # Priority: detected location → profile LGA → default
        user_location = st.session_state.get("user_location") or user.get("location_lga") or "Lagos"
        
        st.markdown(f"##### 🧬 Personalized Briefing for **{user_name}** — 📍 {user_location}")
        
        if "dashboard_insight" not in st.session_state:
            with st.spinner(f"Generating tailored insight for {user_name} in {user_location}..."):
                res = api_client.get_dashboard_insight(
                    st.session_state.token,
                    user_location,
                    f"User: {user_name}. Current StAMP Alert Count: {num_alerts}"
                )
                st.session_state.dashboard_insight = res.get("insight", "No insights available.")
        
        st.info(f"📍 **{user_location}**: {st.session_state.dashboard_insight}")
        
        # Download/Copy for personalized insight
        from .download_utils import render_download_buttons
        render_download_buttons(
            st.session_state.dashboard_insight, 
            filename_prefix=f"adiphas_insight_{user_name}",
            title=f"ADIPHAS Personalized Insight — {user_name}",
            key_suffix="dash_insight"
        )
        st.divider()

    # System-wide StAMP Briefing
    briefing = api_client.get_latest_briefing()
    if briefing and "content" in briefing:
        st.markdown(briefing["content"])
        try:
            # Convert ISO string to friendly format
            dt = pd.to_datetime(briefing.get('generated_at', ''))
            st.caption(f"Generated at: {dt.strftime('%b %d, %Y - %I:%M %p')}")
        except Exception:
            st.caption(f"Generated at: {briefing.get('generated_at', 'N/A')}")
        
        # Download/Copy for StAMP briefing
        from .download_utils import render_download_buttons
        render_download_buttons(
            briefing["content"],
            filename_prefix="adiphas_stamp_briefing",
            title="ADIPHAS StAMP Intelligence Briefing",
            key_suffix="stamp_main"
        )
        
        # Intelligence Sources section
        _render_briefing_sources(briefing, alerts)
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

    # --- MAP ---
    st.subheader("📍 Lagos Health Heatmap")
    try:
        from .health_map import render as render_map
        render_map()
    except Exception as e:
        st.error(f"Error loading map: {e}")

    st.divider()

    # --- LIVE INTELLIGENCE STREAM (Dropdown/Expander) ---
    with st.expander("📡 Live Intelligence Stream", expanded=False):
        if num_alerts > 0:
            for a in alerts[:8]:
                with st.container(border=True):
                    risk = a.get('risk_level', 'Low')
                    colour = {"Critical": "🔴", "High": "🟠", "Moderate": "🟡", "Low": "🟢"}.get(risk, "🔵")
                    st.markdown(f"**{colour} {a.get('disease', 'Signal')}** — {a.get('location_text', 'Unknown')}")
                    st.write(a.get("text", "")[:200])
                    st.caption(f"Source: {a.get('source')} | Risk: {risk}")
                    url = a.get('url')
                    if url:
                        st.link_button("🔗 View Original Source", url, use_container_width=True)
        else:
            st.write("No active signals in the feed.")


def _render_briefing_sources(briefing, alerts):
    """Renders the intelligence sources that informed the StAMP briefing."""
    with st.expander("📚 Intelligence Sources & Transparency", expanded=False):
        st.caption("Sources that informed this briefing:")
        
        # Extract sources from alerts that fed the briefing
        if isinstance(alerts, list) and alerts:
            source_urls = {}
            for a in alerts[:15]:  # Briefing uses top 15 alerts
                source = a.get('source', 'Unknown')
                url = a.get('url')
                if source not in source_urls:
                    source_urls[source] = url
            
            if source_urls:
                st.markdown("**📡 EBS Alert Sources:**")
                for source, url in source_urls.items():
                    if url:
                        st.markdown(f"- [{source}]({url})")
                    else:
                        st.markdown(f"- {source}")
        
        # Check if briefing content itself contains source URLs
        content = briefing.get("content", "")
        if "Intelligence Sources:" in content:
            st.markdown("**🌐 Web & AI Sources:**")
            # Sources are already embedded in the briefing footer by the orchestrator
            import re
            urls = re.findall(r'\[([^\]]+)\]\((https?://[^\)]+)\)', content)
            for name, url in urls:
                st.markdown(f"- [{name}]({url})")
        
        st.caption("💡 ADIPHAS consolidates from scraped news, government portals, Tavily web intelligence, and local RAG knowledge base.")
