import streamlit as st
import api_client
import time
import modules.geolocation as geolocation

def render_login_modal():
    """
    Renders the authentication interface. 
    Uses a centered layout to simulate a modal/overlay effect.
    """
    
    # Custom CSS to simplify the login card
    st.markdown("""
        <style>
            .auth-card {
                padding: 2rem;
                border-radius: 12px;
                max-width: 400px;
                margin: 0 auto;
            }
            .google-btn-container {
                display: flex;
                justify-content: center;
                margin-top: 1rem;
            }
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.subheader("🔐 Access ADIPHAS")
        if "active_auth_tab" not in st.session_state:
            st.session_state.active_auth_tab = "Login"

        tab_c1, tab_c2, tab_c3 = st.columns(3)
        with tab_c1:
            if st.button("Login", use_container_width=True, type="primary" if st.session_state.active_auth_tab == "Login" else "secondary"):
                st.session_state.active_auth_tab = "Login"
                st.rerun()
        with tab_c2:
            if st.button("Sign Up", use_container_width=True, type="primary" if st.session_state.active_auth_tab == "Sign Up" else "secondary"):
                st.session_state.active_auth_tab = "Sign Up"
                st.rerun()
        with tab_c3:
            if st.button("Forgot Password", use_container_width=True, type="primary" if st.session_state.active_auth_tab == "Forgot Password" else "secondary"):
                st.session_state.active_auth_tab = "Forgot Password"
                st.rerun()
        
        st.write("") # small spacing
        selected_tab = st.session_state.active_auth_tab
        
        if selected_tab == "Login":
            reset_token = st.query_params.get("reset_token")
            if reset_token:
                st.info("🔑 Password Reset Mode")
                new_pass1 = st.text_input("New Password", type="password", key="reset_p1")
                new_pass2 = st.text_input("Confirm Password", type="password", key="reset_p2")
                if st.button("Reset Password", type="primary"):
                    if not new_pass1 or new_pass1 != new_pass2:
                        st.error("Passwords must match and cannot be empty.")
                    else:
                        with st.spinner("Resetting password..."):
                            res = api_client.reset_password(reset_token, new_pass1)
                            if res and "msg" in res and "success" in str(res.get("msg")).lower():
                                st.success("Password successfully reset! You can now log in.")
                                # Clear token from URL
                                st.query_params.clear()
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(f"Reset Failed: {res.get('detail', 'Unknown error')}")
            else:
                user_input = st.text_input("Username")
                pass_input = st.text_input("Password", type="password")
                submit_btn = st.button("Login", type="primary")
                    
                if submit_btn:
                    if not user_input or not pass_input:
                        st.error("Please enter both username and password.")
                    else:
                        with st.spinner("Authenticating..."):
                            res = api_client.login(user_input, pass_input)
                            if "access_token" in res:
                                token = res["access_token"]
                                st.session_state.authenticated = True
                                st.session_state.token = token
                                st.query_params["session_token"] = token
                                # Fetch full profile
                                me = api_client.get_me(token)
                                if "username" in me:
                                    st.session_state.user = me
                                    
                                    # --- Resilient location detection on sign-in ---
                                    detected_loc = st.session_state.get('user_location')
                                    profile_loc = me.get('location_lga') or me.get('state')
                                    
                                    # If no detected location yet, try IP-based fallback
                                    if not detected_loc:
                                        try:
                                            detected_loc = geolocation._geolocate_by_ip()
                                        except Exception:
                                            pass
                                    
                                    loc = detected_loc if detected_loc else profile_loc
                                    loc_msg = f" | Location: {loc}" if loc else ""
                                    
                                    # Auto-update profile location if detected and different/missing
                                    if detected_loc and detected_loc != profile_loc:
                                        try:
                                            updated = api_client.update_profile(token, {
                                                "username": me.get("username", "Unknown"), 
                                                "location_lga": detected_loc
                                            })
                                            if updated and "username" in updated:
                                                st.session_state.user = updated
                                                me = updated
                                        except Exception:
                                            pass  # Non-critical — profile update can happen later
                                    
                                    if not me.get('location_lga') and me.get('role', 'CITIZEN') != 'ADMIN':
                                        st.warning(f"Welcome {me.get('username')}!{loc_msg} Please complete your profile to enable personalized alerts.")
                                    else:
                                        st.success(f"Welcome back, {me.get('username')}!{loc_msg}")
                                    
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"Login failed: {me.get('detail', 'Profile error')}")
                            else:
                                st.error(f"Login failed: {res.get('detail', 'Invalid credentials')}")

                st.info("Forgot your password? Select the 'Forgot Password' tab above.")
        
        elif selected_tab == "Forgot Password":
            st.info("🔑 **Password Reset**")
            st.write("Enter your email or username to receive a reset link.")
            reset_email = st.text_input("Email / Username", key="reset_req_email")
            if st.button("Send Reset Link"):
                if reset_email:
                    with st.spinner("Sending link..."):
                        res = api_client.request_password_reset(reset_email)
                        if res and "msg" in res:
                            st.success(res["msg"])
                        else:
                            st.error("Failed to process request.")
                else:
                    st.warning("Please enter your email or username.")

        elif selected_tab == "Sign Up":
            st.info("💡 **Tip:** Complete your profile to receive hyper-tailored health insights and outbreak alerts for your area.")
            
            detected_loc = st.session_state.get('user_location')
            
            # --- LOCATION DETECTION ---
            loc_col1, loc_col2 = st.columns([2, 1])
            with loc_col1:
                if detected_loc:
                    st.success(f"📍 Location detected: **{detected_loc}**")
                else:
                    st.warning("📍 Location not detected yet.")
            with loc_col2:
                st.button("📍 Detect Location", type="secondary",
                          key="signup_geo_btn", on_click=geolocation.request_location_fetch)
                if st.session_state.get("_geo_fetch_requested"):
                    st.caption("⏳ Requesting GPS... allow the prompt.")
            
            st.divider()

            # --- SIGNUP FIELDS ---
            new_user = st.text_input("Desired Username", key="su_user")
            new_email = st.text_input("Email Address", key="su_email")
            new_pass = st.text_input("Password", type="password", key="su_pass")
            new_full_name = st.text_input("Full Name", key="su_name")
            new_role = st.selectbox("I am a...", ["CITIZEN", "EXPERT"], key="su_role")
            
            final_loc_input = st.text_input("Home Location (LGA)", value=detected_loc if detected_loc else "", help="Auto-filled if you clicked 'Detect Location'. You can also type it manually.")
            
            signup_btn = st.button("Create Account", type="primary")
            
            if signup_btn:
                if not new_user or not new_pass or not new_email:
                    st.error("Please fill in all required fields.")
                else:
                    with st.spinner("Creating account & setting up profile..."):
                        # Immediate geocoding to ensure map marker is ready
                        if final_loc_input:
                            coords = geolocation._forward_geocode_nominatim(final_loc_input)
                            if coords:
                                st.session_state.user_lat, st.session_state.user_lon = coords
                                st.session_state.user_location = final_loc_input
                        
                        res = api_client.register(new_user, new_pass, new_email, new_full_name, new_role, final_loc_input)
                        if "id" in res:
                            st.success("✅ Account created successfully! Please switch to the Login tab.")
                        else:
                            st.error(f"Signup Failed: {res.get('detail', 'Unknown error')}")

def logout():
    """Clears session state and logs the user out."""
    st.session_state.clear()
    st.session_state.authenticated = False
    st.session_state.token = None
    st.session_state.user = None
    st.rerun()
