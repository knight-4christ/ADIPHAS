import streamlit as st
import api_client
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

def render_heartbeat():
    """Renders a smooth, slow-moving system monitor."""
    st.markdown("""
        <style>
        .monitor-container {
            width: 100%;
            height: 60px;
            background: transparent;
            overflow: hidden;
            position: relative;
            display: flex;
            align-items: center;
        }

        /* The moving line */
        .wave-path {
            fill: none;
            stroke: #4ade80; /* bright green */
            stroke-width: 2;
            stroke-linecap: round;
            /* Dash matches the total length of the path roughly */
            stroke-dasharray: 1000; 
            stroke-dashoffset: 1000;
            animation: draw 8s linear infinite; /* Slower 8s animation */
        }
        
        @keyframes draw {
            from { stroke-dashoffset: 1000; }
            to { stroke-dashoffset: 0; }
        }
        
        /* Fade mask at edges - Dynamic based on theme */
        .monitor-fade {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: linear-gradient(90deg, 
                var(--bg-color-ekg) 0%, 
                transparent 10%, 
                transparent 90%, 
                var(--bg-color-ekg) 100%);
            pointer-events: none;
        }
        </style>
        
        <script>
            // Inject theme variable into CSS for the SVG monitor
            const isDark = window.parent.document.body.getAttribute('data-is-dark-theme') === 'true';
            const bg = getComputedStyle(window.parent.document.body).backgroundColor;
            document.documentElement.style.setProperty('--bg-color-ekg', bg);
        </script>
        
        <div class="monitor-container">
            <svg viewBox="0 0 500 50" preserveAspectRatio="none" width="100%" height="100%">
                <!-- Realistic EKG: Flat -> P-wave -> QRS Complex -> T-wave -> Flat -->
                <!-- Repeated pattern for the animation loop -->
                <path class="wave-path" d="
                    M0,25 L50,25 L60,20 L70,30 L80,25  
                    L90,25 L95,40 L105,5 L115,45 L120,25 
                    L130,25 L140,20 L150,30 L160,25 L500,25" />
            </svg>
            <div class="monitor-fade"></div>
        </div>
    """, unsafe_allow_html=True)

def render():
    # NO st_autorefresh — user clicks "Refresh" manually to avoid UI blur
    
    st.title("🛡️ ADIPHAS Command Centre")
    
    # Check System Status
    status = api_client.healthcheck()
    is_online = isinstance(status, dict) and status.get("status") == "ok"
    
    t_status, t_ai, t_engine, t_monitor, t_hub = st.tabs([
        "🔌 System Status",
        "🧠 AI Summary",
        "📡 Engine Status",
        "📊 Live Monitoring",
        "🔐 Verification Hub"
    ])
    
    with t_status:
        # Status Header
        if is_online:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                st.success("✅ **SYSTEM ONLINE**")
            with col2:
                st.info(f"🤖 Active Agents: {status.get('agents_active', 4)}")
            with col3:
                st.caption("System Pulse")
                render_heartbeat()
        else:
            st.warning("💤 **System is Resting**")
            st.write("The intelligence engine is currently offline. Please check back in a moment.")
            
            with st.expander("🛠️ Developer Diagnostics"):
                st.error("Connection Refused (WinError 10061)")
                st.code("Backend unreachable at http://localhost:8000")
                if st.button("Retry Connection"):
                    st.rerun()

    with t_ai:
        # --- AI Startup Insight (generated once at server start) ---
        startup = api_client.get_startup_insight()
        if isinstance(startup, dict) and startup.get("insight"):
            st.markdown("### 🧠 AI Intelligence Summary")
            st.info(f"**So Far...** {startup['insight']}")
            if startup.get("generated_at"):
                st.caption(f"Generated at server startup: {startup['generated_at']}")
        else:
            st.info("No AI insights generated yet.")
    
    with t_engine:
        # --- Intelligence Engine Metrics (Real-time auto-refresh) ---
        st.markdown("### 📡 Intelligence Engine Status")

        @st.fragment(run_every="5s")
        def render_realtime_metrics():
            metrics = api_client.get_system_metrics()
            
            if isinstance(metrics, dict) and not metrics.get("error"):
                m1, m2, m3 = st.columns(3)
                agent_counts = metrics.get("today_activity_by_agent", {})
                m1.metric("📰 Total Alerts in DB", metrics.get("total_alerts_in_db", 0))
                m2.metric("✅ Verified Alerts", metrics.get("verified_alerts", 0))
                m3.metric("⚙️ Today's Agent Actions", sum(agent_counts.values()))

                # --- NEW: Scraping Performance Section ---
                st.markdown("#### 🕵️‍♂️ Autonomous Scraper Performance")
                s1, s2, s3 = st.columns(3)
                s1.metric("Articles Found", metrics.get("last_scrape_articles", 0))
                s2.metric("Skipped (Old)", metrics.get("articles_skipped", 0))
                s3.metric("New Data Processed", metrics.get("articles_new", 0))
                
                sources = metrics.get("last_scrape_sources", "None")
                if sources != "None":
                    st.caption(f"📍 **Recent Sources:** {sources}")
                
                # Token Usage
                token_data = api_client.get_token_usage()
                model_status = api_client.get_model_status()
                
                if isinstance(token_data, dict) and not token_data.get("error"):
                    with st.expander("🔑 Gemini AI Status & Token Usage", expanded=True):
                        # Model Status Header
                        if isinstance(model_status, dict) and not model_status.get("error"):
                            cur_model = model_status.get("current_model", "Unknown")
                            switches = model_status.get("switch_count", 0)
                            st.markdown(f"**Active Model:** `{cur_model}` " + (f" (Fallback active: {switches} switches)" if switches > 0 else ""))
                            st.divider()

                        t1, t2, t3 = st.columns(3)
                        t1.metric("Prompt Tokens", token_data.get("prompt_tokens", 0))
                        t2.metric("Response Tokens", token_data.get("candidate_tokens", 0))
                        t3.metric("Total Tokens", token_data.get("total_tokens", 0))
                        st.caption(f"API Calls: {token_data.get('call_count', 0)} | Snapshot: {token_data.get('snapshot_time', 'N/A')}")
            else:
                st.warning("Could not retrieve system metrics.")

        # Call the fragment immediately so it renders and starts its 5s refresh loop
        render_realtime_metrics()
        
        st.write("---")
        if st.button("🔄 Refresh Dashboard", type="primary"):
            st.rerun()

    with t_monitor:
        st.subheader("📡 Live System Monitoring")
        
        @st.fragment(run_every="10s")
        def render_live_monitoring():
            try:
                alerts = api_client.get_alerts()
                last_check = st.session_state.get('last_checked_alerts', '1970-01-01T00:00:00')
                
                unread_count = 0
                if isinstance(alerts, list):
                    for a in alerts:
                        ts = a.get('timestamp', '')
                        created_ts = a.get('created_at', ts)
                        if created_ts > last_check:
                            unread_count += 1
                
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.metric("New Unread Insights", unread_count, delta=f"+{unread_count}" if unread_count > 0 else None)
                    if unread_count > 0:
                        st.write("Go to **Local Health Feed** to review them.")
                    
                with c2:
                    if isinstance(alerts, list) and alerts:
                        # Guard: validate we have a proper list of dicts with 'created_at' before building DataFrame
                        valid_alerts = [a for a in alerts if isinstance(a, dict) and 'created_at' in a]
                        if valid_alerts:
                            # Intelligence Pulse Chart
                            df_alerts = pd.DataFrame(valid_alerts)
                            df_alerts['date'] = pd.to_datetime(df_alerts['created_at'], errors='coerce').dt.date
                            df_alerts = df_alerts.dropna(subset=['date'])
                            pulse = df_alerts.groupby('date').size().reset_index(name='count')
                            
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                x=pulse['date'], y=pulse['count'],
                                mode='lines+markers',
                                name='Signals Found',
                                line=dict(color='#0ea5e9', width=3),
                                fill='tozeroy'
                            ))
                            fig.update_layout(
                                title="System Intelligence Pulse (Signals per Day)",
                                height=200, margin=dict(l=0, r=0, t=30, b=0),
                                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#334155')
                            )
                            st.plotly_chart(fig, width='stretch')

                st.write("---")
                
                # Activity Log
                col_log_title, col_log_date = st.columns([2, 1])
                with col_log_title:
                    st.subheader("📝 Agent Transaction Log")
                with col_log_date:
                    selected_date = st.date_input("View History", datetime.now().date(), key="activity_log_date")

                if selected_date == datetime.now().date():
                    activities = api_client.get_activity()
                else:
                    activities = api_client.get_activity_history(selected_date.strftime("%Y-%m-%d"))
                    
                if isinstance(activities, list) and activities:
                    valid_activities = [a for a in activities if isinstance(a, dict)]
                    df_log = pd.DataFrame(valid_activities)
                    if not df_log.empty and 'timestamp' in df_log.columns:
                        cols = [c for c in ['timestamp', 'agent', 'message'] if c in df_log.columns]
                        df_display = df_log[cols].copy()
                        df_display['timestamp'] = df_display['timestamp'].apply(
                            lambda x: x.replace('T', ' ').split(' ')[1][:8] if isinstance(x, str) and (' ' in x or 'T' in x) else x
                        )
                        st.dataframe(df_display, hide_index=True, width='stretch')
                else:
                    st.info("System initializing... No activities logged yet.")
                    
            except Exception as e:
                st.error(f"Error refreshing dashboard: {e}")

        # Execute monitoring fragment
        render_live_monitoring()

    with t_hub:
        st.markdown("### 🔐 Official Channels & Verification Hub")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### National Agencies")
            st.markdown("- [NCDC](https://ncdc.gov.ng)")
            st.markdown("- [Federal Ministry of Health](https://health.gov.ng)")
        with col2:
            st.markdown("#### Emergency Contacts")
            st.markdown("**NCDC Toll Free:** 6232")
