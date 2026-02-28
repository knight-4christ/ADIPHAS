import streamlit as st
import api_client
import pandas as pd

def render():
    from streamlit_autorefresh import st_autorefresh
    # Auto-refresh the EBS dashboard every 60 seconds for experts
    st_autorefresh(interval=60000, limit=None, key="ebs_autorefresh")
    
    st.title("🚨 Expert Verification Panel")
    st.caption("Event-Based Surveillance (EBS) Alert Management")
    
    tab1, tab2 = st.tabs(["🔍 Pending Alerts", "🧠 Knowledge Fusion"])
    
    with tab1:
        # Use cached alerts from app.py
        alerts = st.session_state.get("cached_alerts")
        if not alerts:
            alerts = api_client.get_alerts()
            
        if not isinstance(alerts, list):
            st.error("Unable to load alerts. Backend may be offline.")
            return
        
        # Filter for unverified and Sort by Recency
        pending = [a for a in alerts if not a.get('verified')]
        pending.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Search Filter
        search_query = st.text_input("🔍 Search alerts by disease or location...", placeholder="e.g. Cholera")
        if search_query:
            pending = [
                a for a in pending 
                if search_query.lower() in (a.get('disease') or "").lower() or 
                   search_query.lower() in (a.get('location_text') or "").lower()
            ]
        
        if pending:
            st.write(f"Showing {len(pending)} pending alerts.")
            
            for alert in pending:
                with st.expander(f"{alert.get('risk_level', 'Unknown')} Risk: {alert.get('text', 'Alert')}", expanded=True):
                    if alert.get('requires_hitl'):
                        st.error("🛑 **MANDATORY HITL**: This signal was discovered via Autonomous Recovery or is High Severity without official confirmation.")
                    if alert.get('policy_alert'):
                        st.warning("⚖️ **Policy Watch**: This alert contains mentions of administrative renaming (Area Administrative Councils).")
                        
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**Location:** {alert.get('location_text')}")
                        st.markdown(f"**🛡️ Evidence Trace:** Source: {alert.get('source', 'Autonomous Agent')} (ID: {alert.get('alert_id')[:8]})")
                        st.markdown(f"**Timestamp:** {alert.get('timestamp')}")
                        
                        # RAG Verification
                        if st.button("🔍 Cross-Reference Intelligence", key=f"rag_{alert['alert_id']}"):
                            with st.spinner("Searching local & global context..."):
                                sq = f"{alert.get('disease')} outbreaks in {alert.get('location_text')} Nigeria"
                                rres = api_client.advisory_search(sq)
                                if rres and not rres.get("error"):
                                    st.info(f"Source: {rres.get('source').upper()}")
                                    for rs in rres.get('results', [])[:2]:
                                        st.caption(rs.get('content') or rs.get('snippet') or str(rs))
                                else:
                                    st.write("No similar context found.")
                    with col2:
                        if st.button("✅ Verify & Publish", key=f"verify_{alert['alert_id']}"):
                            res = api_client.verify_alert(st.session_state.token, alert['alert_id'])
                            if "status" in res:
                                st.cache_data.clear() # Clear global alerts cache
                                st.session_state.success_banner = f"Intelligence Signal {alert['alert_id'][:8]} verified and published!"
                                st.rerun()
                        
                        if st.button("🗑️ Discard", key=f"discard_{alert['alert_id']}"):
                            res = api_client.discard_alert(st.session_state.token, alert['alert_id'])
                            st.cache_data.clear() # Clear global alerts cache
                            st.session_state.success_banner = f"Intelligence Signal {alert['alert_id'][:8]} discarded successfully."
                            st.rerun()
        else:
            st.success("No pending alerts! All autonomous findings have been reviewed.")
            
    with tab2:
        st.subheader("Knowledge Fusion Simulator")
        st.write("Simulate conflicting reports to see how the agent resolves them using **Dempster-Shafer Logic**.")
        
        # Fetch Real Sources from Backend
        source_registry = api_client.get_intelligence_sources()
        if not isinstance(source_registry, dict) or "error" in source_registry:
            # Fallback to defaults if backend offline
            source_registry = {"NCDC": 0.95, "Punch Health": 0.7, "SOCIAL_MEDIA": 0.3}
            
        source_list = sorted(list(source_registry.keys()))
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### Source A")
            src_a = st.selectbox("Select Source A", source_list, index=source_list.index("NCDC") if "NCDC" in source_list else 0)
            weight_a = source_registry.get(src_a, 0.5)
            st.caption(f"Reliability Weight: **{weight_a}**")
            cases_a = st.number_input("Reported Cases (A)", value=50, key="cases_a_sim")
            loc_a = st.text_input("Location (A)", value="Ikeja", key="loc_a_sim")
            
        with c2:
            st.markdown("### Source B")
            src_b = st.selectbox("Select Source B", source_list, index=source_list.index("Punch Health") if "Punch Health" in source_list else 0)
            weight_b = source_registry.get(src_b, 0.5)
            st.caption(f"Reliability Weight: **{weight_b}**")
            cases_b = st.number_input("Reported Cases (B)", value=10, key="cases_b_sim")
            loc_b = st.text_input("Location (B)", value="Ikeja", key="loc_b_sim")
            
        if st.button("Run Fusion Algorithm", use_container_width=True):
            with st.spinner("Calculating Dempster-Shafer Consensus..."):
                reports = [
                    {"source": src_a, "cases": cases_a, "location": loc_a, "disease": "Cholera"},
                    {"source": src_b, "cases": cases_b, "location": loc_b, "disease": "Cholera"}
                ]
                try:
                    result = api_client.fuse_intelligence(reports)
                    st.success("Mathematical Fusion Complete")
                    
                    # Report View
                    st.markdown("### 📄 Intelligence Report")
                    st.markdown(f"**Consensus Location:** {result.get('location')}")
                    st.markdown(f"**Confidence Score:** {result.get('confidence_score')}")
                    st.markdown(f"**Resolved Case Count:** `{result.get('estimated_cases')}`")
                    
                    # AI Semantic Synopsis & Advisory
                    ai_synopsis = result.get("ai_synopsis")
                    fused_advisory = result.get("fused_advisory")
                    
                    if ai_synopsis:
                        st.subheader("🧠 Intelligence Fusion")
                        st.info(f"**Synopsis**: {ai_synopsis}")
                        if fused_advisory:
                            st.warning(f"💊 **Fused Advisory**: {fused_advisory}")
                    else:
                        st.info(f"**Status**: {result.get('status')}")
                    
                    with st.expander("View Logic Trace"):
                        for step in result.get("trace", []):
                            st.text(f"[{step['timestamp']}] {step['step']}")
                            
                except Exception as e:
                    st.error(f"Fusion Error: {e}")
