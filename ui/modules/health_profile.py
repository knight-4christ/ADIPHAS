import streamlit as st
import api_client
import pandas as pd
from datetime import datetime

def render(force_completion: bool = False):
    st.title("👤 My Health Profile")
    st.caption("Manage your personal health profile, geospatial anchoring, and intelligence delivery settings.")
    
    user = st.session_state.user
    
    # --- MANDATORY COMPLETION BANNER ---
    if force_completion:
        st.error("🚨 **Action Required**: You must complete ALL bio-data fields below before accessing other modules. This ensures you receive personalized health intelligence tailored to your profile.")
        
        # Email verification suspended
        # if not user.get('is_email_verified'):
        #     st.info("💡 **Tip**: Check your inbox for a verification link. Once clicked, use the button below to unlock the system.")
        #     if st.button("🔄 Refresh My Status", key="refresh_status_btn", type="primary"):
        #         with st.spinner("Checking verification..."):
        #             updated_user = api_client.get_me(st.session_state.token)
        #             if updated_user and "id" in updated_user:
        #                 st.session_state.user = updated_user
        #                 if not updated_user.get('is_email_verified'):
        #                     st.warning("⚠️ Email not yet verified. Please check your email inbox and click the verification link.")
        #                 else:
        #                     st.success("✅ Status updated! Email is verified.")
        #                     st.rerun()
        #             else:
        #                 err_msg = updated_user.get('detail') if isinstance(updated_user, dict) else str(updated_user)
        #                 st.error(f"Failed to refresh status: {err_msg}")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Impact Score
        st.metric("Community Impact Score", f"⭐ {user.get('impact_score', 0)}")
        st.caption("Earn points by verifying alerts and logging vitals.")
        
        st.write("---")
        st.write("**Account Info**")
        st.text(f"Username: {user.get('username')}")
        st.text(f"Role: {user.get('role')}")
        
        # Show which fields are missing
        if force_completion:
            st.write("---")
            st.markdown("**📋 Completion Status:**")
            fields_status = {
                "Email Verified": user.get('is_email_verified'),
                "Blood Group": user.get('blood_group'),
                "Genotype": user.get('genotype'),
                "Location": user.get('location_lga'),
                "Health Conditions": user.get('health_conditions'),
            }
            for field_name, value in fields_status.items():
                if value and str(value).strip() and value != 'None':
                    st.markdown(f"✅ {field_name}")
                else:
                    st.markdown(f"❌ **{field_name}** — Required")
        
    with col2:
        st.subheader("Edit Bio-Data")
        
        # --- LOCATION DETECTION (Button-based via streamlit-js-eval) ---
        st.markdown("**📍 Current Location**")
        current_loc = user.get('location_lga', '')
        detected_loc = st.session_state.get('user_location')
        
        loc_col1, loc_col2 = st.columns([2, 1])
        with loc_col1:
            if current_loc:
                st.success(f"📍 Location set: **{current_loc}**")
            elif detected_loc:
                st.info(f"🛰️ Detected: **{detected_loc}** — click 'Save Location' to apply")
            else:
                st.warning("📍 No location set yet — click the button to detect →")
        
        with loc_col2:
            if detected_loc and detected_loc != current_loc:
                # Location already detected — offer to save it to the profile
                if st.button("💾 Save Location", width="stretch", type="primary"):
                    res = api_client.update_profile(st.session_state.token, {
                        "username": user.get("username", "Unknown"),
                        "location_lga": detected_loc
                    })
                    if res and "username" in res:
                        st.session_state.user = res
                        st.success(f"✅ Location saved: **{detected_loc}**")
                        st.rerun()
                    else:
                        st.error("Failed to save location.")
            else:
                # No location detected yet — trigger GPS fetch
                import modules.geolocation as geolocation
                st.button("📍 Detect My Location", width="stretch", type="primary",
                         key="profile_geo_btn", on_click=geolocation.request_location_fetch)
                if st.session_state.get("_geo_fetch_requested"):
                    st.caption("⏳ Requesting browser GPS... allow the permission prompt.")
        
        st.divider()
        
        with st.form("edit_profile"):
            # Added username editing
            new_username = st.text_input("Username / ID", value=user.get('username', ''))
            
            c1, c2 = st.columns(2)
            
            # Set current values for dropdowns
            bg_options = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
            current_bg = user.get('blood_group', '')
            bg_index = bg_options.index(current_bg) if current_bg in bg_options else 0
            
            gt_options = ["AA", "AS", "SS", "AC"]
            current_gt = user.get('genotype', '')
            gt_index = gt_options.index(current_gt) if current_gt in gt_options else 0
            
            bg = c1.selectbox("Blood Group *", bg_options, index=bg_index)
            gt = c2.selectbox("Genotype *", gt_options, index=gt_index)
            
            address = st.text_input("Residential Address", value=user.get('address', ''))
            
            manual_lga = st.text_input("Location (LGA or City) *", value=user.get('location_lga', ''), placeholder="e.g., Yaba, Ikeja, Lagos Mainland")
            
            conditions = st.text_area(
                "Underlying Health Conditions *", 
                value=user.get('health_conditions', ''),
                placeholder="e.g., Asthma, Diabetes, Hypertension, or 'None' if healthy",
                help="Enter 'None' if you have no underlying conditions. This field is required."
            )
            
            if force_completion:
                st.info("💡 All fields marked with * are mandatory. Click 'Detect My Location' above to set your location. Enter 'None' for health conditions if you have no underlying conditions.")
            
            submitted = st.form_submit_button("Update Profile", width="stretch")
            if submitted:
                # Validate all required fields
                validation_errors = []
                if not bg:
                    validation_errors.append("Blood Group is required")
                if not gt:
                    validation_errors.append("Genotype is required")
                if not manual_lga.strip() and not detected_loc:
                    validation_errors.append("Location is required — enter it manually or click 'Detect My Location' above")
                if not conditions or not conditions.strip():
                    validation_errors.append("Health Conditions is required (enter 'None' if healthy)")
                
                if validation_errors:
                    for err in validation_errors:
                        st.error(f"❌ {err}")
                else:
                    update_data = {
                        "username": new_username,
                        "blood_group": bg,
                        "genotype": gt,
                        "health_conditions": conditions.strip(),
                        "location_lga": manual_lga.strip() if manual_lga.strip() else detected_loc
                    }
                    
                    with st.spinner("Updating..."):
                        res = api_client.update_profile(st.session_state.token, update_data)
                        if "username" in res:
                            st.session_state.user = res
                            # Forcefully purge Streamlit's global geocache to adopt the user's manual override immediately
                            new_loc = update_data["location_lga"]
                            st.session_state.user_location = new_loc
                            
                            # Hard-reset the latitude and longitude caches so the Map moves from Oregon!
                            try:
                                import requests
                                # Ping OpenStreetMap to mathematically geocode the typed string
                                geocode_url = f"https://nominatim.openstreetmap.org/search?q={new_loc}, Nigeria&format=json&limit=1"
                                resp = requests.get(geocode_url, headers={"User-Agent": "ADIPHAS/1.0"}, timeout=4)
                                if resp.status_code == 200 and len(resp.json()) > 0:
                                    st.session_state.user_lat = float(resp.json()[0]['lat'])
                                    st.session_state.user_lon = float(resp.json()[0]['lon'])
                            except Exception:
                                pass
                                
                            st.success("✅ Profile Updated Successfully!")
                            if force_completion:
                                st.balloons()
                                st.info("🎉 Profile complete! You now have access to all modules. Refreshing...")
                            st.rerun()
                        else:
                            st.error("Update failed.")

    st.divider()
    
    # --- HEALTH TRACKER (Symptoms Only) — hide during forced completion ---
    if not force_completion:
        st.subheader("🩺 Health Tracker & Advisory")
        
        st.write("Analyze symptoms against autonomous disease intelligence.")
        with st.form("symptom_form"):
            symptoms = st.multiselect("Select Symptoms", 
                ["Fever", "Bleeding", "Headache", "Vomiting", "Diarrhea", "Rice-water stool", "Chills", "Sore throat", "Rash"]
            )
            duration = st.slider("Duration (days)", 1, 14, 1)
            
            if st.form_submit_button("Assess Risk"):
                if symptoms:
                    payload = {
                        "symptoms": symptoms, 
                        "duration_days": duration,
                        "user_id": st.session_state.user.get("id"),
                        "timestamp": datetime.now().isoformat()
                    }
                    with st.spinner("Consulting Advisory Engine..."):
                        result = api_client.assess_symptoms(payload)
                    
                    st.divider()
                    # Display Risk
                    risk_score = result.get("risk_score", 0)
                    st.progress(risk_score)
                    
                    cat = result.get("risk_category", "Low")
                    if "CRITICAL" in cat.upper():
                        st.error(f"🚨 {cat}")
                    elif "HIGH" in cat.upper():
                        st.warning(f"⚠️ {cat}")
                    else:
                        st.success(f"✅ {cat}")
                    
                    # AI Situational Summary
                    ai_summary = result.get("ai_situational_summary")
                    if ai_summary:
                        st.info(f"🛡️ **AI Situational Risk**: {ai_summary}")

                    # AI Clinical Insight
                    ai_insight = result.get("ai_clinical_insight")
                    if ai_insight:
                        st.success(f"🩺 **AI Clinical Insight**: {ai_insight}")
                        
                    st.write("**Personalized Advisory:**")
                    for sug in result.get("suggestions", []):
                        st.markdown(f"- {sug}")
                else:
                    st.info("Select symptoms to begin.")

    # --- INTELLIGENCE & ACCOUNT SETTINGS ---
    if not force_completion:
        st.divider()
        st.subheader("📩 Intelligence & Account Settings")
        
        c1, c2 = st.columns(2)
        
        with c1:
            st.markdown("**Email Verification**")
            email = user.get("email")
            if not email:
                st.warning("No email associated with this account.")
            else:
                is_verified = user.get("is_email_verified", False)
                if is_verified:
                    st.success(f"✅ Verified: `{email}`")
                else:
                    st.error(f"❌ Unverified: `{email}`")
                    if st.button("Resend Verification Email", key="resend_ver_btn"):
                        with st.spinner("Resending..."):
                            res = api_client.resend_verification(st.session_state.token)
                            if res and "msg" in res:
                                st.success(res["msg"])
                            else:
                                st.error("Failed to resend.")

        with c2:
            st.markdown("**Proactive Briefings**")
            current_briefing = user.get("receive_briefings", True)
            briefing_toggle = st.toggle("Receive automated 2-hour health briefings", value=current_briefing, 
                                      help="If enabled, ADIPHAS will email you tailored situational intelligence every 2 hours.")
            
            if briefing_toggle != current_briefing:
                with st.spinner("Updating settings..."):
                    res = api_client.update_profile(st.session_state.token, {
                        "receive_briefings": briefing_toggle
                    })
                    if res and "id" in res:
                        st.session_state.user = res
                        st.success("Briefing settings updated!")
                        st.rerun()
