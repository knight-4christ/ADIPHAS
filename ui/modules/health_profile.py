import streamlit as st
import api_client
import pandas as pd
from datetime import datetime

# Lagos LGA Coordinates (Approximate Centers) from app.py for consistency
LAGOS_LGAS = [
    "Agege", "Ajeromi-Ifelodun", "Alimosho", "Amuwo-Odofin", "Apapa", "Badagry", 
    "Epe", "Eti-Osa", "Ibeju-Lekki", "Ifako-Ijaiye", "Ikeja", "Ikorodu", 
    "Kosofe", "Lagos Island", "Lagos Mainland", "Mushin", "Ojo", "Oshodi-Isolo", 
    "Shomolu", "Surulere"
]

def render():
    st.title("👤 My Health Profile")
    
    user = st.session_state.user
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Impact Score
        st.metric("Community Impact Score", f"⭐ {user.get('impact_score', 0)}")
        st.caption("Earn points by verifying alerts and logging vitals.")
        
        st.write("---")
        st.write("**Account Info**")
        st.text(f"Username: {user.get('username')}")
        st.text(f"Role: {user.get('role')}")
        
    with col2:
        st.subheader("Edit Bio-Data")
        
        with st.form("edit_profile"):
            # Added username editing
            new_username = st.text_input("Username / ID", value=user.get('username', ''))
            
            c1, c2 = st.columns(2)
            bg = c1.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"], index=0) # Should set index based on current
            gt = c2.selectbox("Genotype", ["AA", "AS", "SS", "AC"], index=0) 
            
            lga = st.selectbox("Current Location (LGA)", LAGOS_LGAS)
            address = st.text_input("Residential Address", value=user.get('address', ''))
            
            conditions = st.text_area("Underlying Conditions", value=user.get('health_conditions', ''))
            
            if st.form_submit_button("Update Profile"):
                update_data = {
                    "username": new_username,
                    "blood_group": bg,
                    "genotype": gt,
                    "location_lga": lga,
                    "health_conditions": conditions
                }
                
                with st.spinner("Updating..."):
                    res = api_client.update_profile(st.session_state.token, update_data)
                    if "username" in res:
                        st.session_state.user = res
                        st.success("Profile Updated Successfully!")
                        st.rerun()
                    else:
                        st.error("Update failed.")

    st.divider()
    
    # --- HEALTH TRACKER (Symptoms Only) ---
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

