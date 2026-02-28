import streamlit as st
import api_client
import pandas as pd
import time
from datetime import datetime

def render():
    from streamlit_autorefresh import st_autorefresh
    # Auto-refresh the feed every 60 seconds
    st_autorefresh(interval=60000, limit=None, key="feed_autorefresh")
    
    st.title("📰 Local Health Intelligence Feed")
    st.caption("Real-time health news and autonomous surveillance data.")
    
    # Intelligence Source Summary
    with st.expander("📡 Autonomous Surveillance Network"):
        st.write("The ADIPHAS agents are currently monitoring **22 verified sources** including NCDC, FMoH, Lagos MoH, and major Nigerian health journalism outlets.")
        st.info("💡 **Scope**: Now tracking 20+ high-impact diseases including Mpox, Lassa Fever, Cholera, and Diphtheria.")

    # Action Bar
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info("💡 This feed aggregates health news from verified sources and social signals.")
    with col2:
        if st.button("🔄 Refresh Feed"):
            st.rerun()

    # Manual Scrape Trigger (Expert/Admin Only)
    if st.session_state.user and st.session_state.user.get('role') in ["ADMIN", "EXPERT"]:
        with st.expander("🕵️‍♂️ Manager Options: Trigger Autonomous Scraper"):
            if st.button("Start Scraper Job"):
                with st.spinner("Agent is scouring the web..."):
                    data = api_client.scrape_news()
                    # /acquisition/news/scrape returns {"status":..,"count":N,"data":[...]}
                    if isinstance(data, dict) and data.get("status") == "success":
                        st.cache_data.clear() # Refresh global alerts
                        st.success(f"Scraped {data.get('count', 0)} new signals from 22 sources.")
                        time.sleep(1)
                        st.rerun()
                    elif isinstance(data, dict) and data.get("error"):
                        st.error(f"Scraper failed: {data.get('detail', 'Unknown error')}")
                    else:
                        st.warning(f"Scraper returned: {data}")

    # News Display
    try:
        # Use cached alerts from app.py to avoid redundant fetch
        alerts = st.session_state.get("cached_alerts")
        if not alerts:
            alerts = api_client.get_alerts()
        
        if isinstance(alerts, list) and alerts:
            # Sort by timestamp descending
            alerts.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            last_check = st.session_state.get('last_checked_alerts', '1970-01-01T00:00:00')
            feed_data = []
            for a in alerts:
                ts = a.get('timestamp', '')
                created_ts = a.get('created_at', str(ts)) # Fallback to timestamp if created_at is missing
                is_new = created_ts > last_check
                
                dt = ts.replace('T', ' ').split(' ')[0] if (' ' in ts or 'T' in ts) else ts
                tm = ts.replace('T', ' ').split(' ')[1][:5] if (' ' in ts or 'T' in ts) else ""
                
                feed_data.append({
                    "Status": "🆕 NEW" if is_new else "✅ Seen",
                    "Date": dt,
                    "Time": tm,
                    "Source": a.get('source', 'Unknown'),
                    "Disease": a.get('disease', 'General'),
                    "Headline": a.get('text', '')
                })
            
            df = pd.DataFrame(feed_data)
            # Sort for grouping
            df['is_new_val'] = df['Status'] == "🆕 NEW"
            df = df.sort_values(by=["is_new_val", "Date", "Time"], ascending=[False, False, False])
            
            new_df = df[df['is_new_val']].drop(columns=['is_new_val'])
            older_df = df[~df['is_new_val']].drop(columns=['is_new_val'])

            if not new_df.empty:
                st.subheader("🆕 Fresh Intelligence")
                st.dataframe(
                    new_df,
                    column_config={
                        "Disease": st.column_config.TextColumn("Disease/Topic", help="Detected entity"),
                        "Status": st.column_config.TextColumn("Status", width="small")
                    },
                    use_container_width=True, 
                    hide_index=True
                )
            
            if not older_df.empty:
                st.subheader("📜 Historical Context")
                st.dataframe(
                    older_df,
                    column_config={
                        "Disease": st.column_config.TextColumn("Disease/Topic", help="Detected entity"),
                        "Status": st.column_config.TextColumn("Status", width="small")
                    },
                    use_container_width=True, 
                    hide_index=True
                )
            
            # Update last checked timestamp for the badge logic
            st.session_state.last_checked_alerts = datetime.utcnow().isoformat()
        else:
            st.info("No recent intelligence found. The autonomous agents are still scanning.")
            
    except Exception as e:
        st.error(f"Could not load news feed: {e}")
