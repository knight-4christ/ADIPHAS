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
        
        # Use horizontal radio as tabs to preserve state across reruns
        selected_tab = st.radio(
            "Auth Tabs", 
            ["Login", "Sign Up", "Forgot Password"], 
            horizontal=True, 
            label_visibility="collapsed",
            key="auth_tab_selector"
        )
        st.write("") # small spacing
        
        if selected_tab == "Login":
            reset_token = st.query_params.get("reset_token")
            if reset_token:
                st.info("🔑 Password Reset Mode")
                new_pass1 = st.text_input("New Password", type="password", key="reset_p1")
                new_pass2 = st.text_input("Confirm Password", type="password", key="reset_p2")
                if st.button("Reset Password", width="stretch", type="primary"):
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
                # --- GOOGLE TOKEN LISTENER (Suspended) ---
                # g_token = st.query_params.get("g_token")
                # if g_token:
                #     with st.spinner("Google Authenticating..."):
                #         res = api_client.google_login(g_token)
                #         if "access_token" in res:
                #             token = res["access_token"]
                #             st.session_state.authenticated = True
                #             st.session_state.token = token
                #             st.session_state.user = api_client.get_me(token)
                #             st.query_params.clear()
                #             st.rerun()
                #         else:
                #             st.error("Google Sign-In Failed.")
                #             st.query_params.clear()

                with st.form("login_form"):
                    user_input = st.text_input("Username")
                    pass_input = st.text_input("Password", type="password")
                    submit_btn = st.form_submit_button("Login", width='stretch')
                    
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

                # --- GOOGLE SIGN-IN BUTTON (Suspended) ---
                # client_id = "581777295975-3e074nkevgksedf84k61fg9e8kutfn13.apps.googleusercontent.com"
                # backend_url = api_client.API_URL
                # redirect_uri = f"{backend_url}/api/auth/google/callback"
                # 
                # google_auth_url = (
                #     f"https://accounts.google.com/o/oauth2/v2/auth?"
                #     f"client_id={client_id}&"
                #     f"response_type=id_token&"
                #     f"redirect_uri={redirect_uri}&"
                #     f"scope=openid%20email%20profile&"
                #     f"nonce=adiphas123"
                # )
                # st.write("")
                # st.link_button("🌐 Continue with Google", url=google_auth_url, use_container_width=True)
                # st.write("")

                # Link-like button to redirect to Forgot Password tab
                st.info("Forgot your password? Select the 'Forgot Password' tab above.")
        
        elif selected_tab == "Forgot Password":
            st.info("🔑 **Password Reset**")
            st.write("Enter your email or username to receive a reset link.")
            reset_email = st.text_input("Email / Username", key="reset_req_email")
            if st.button("Send Reset Link", width="stretch"):
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
            
            # --- LOCATION DETECTION (Outside Form) ---
            loc_col1, loc_col2 = st.columns([2, 1])
            with loc_col1:
                if detected_loc:
                    st.success(f"📍 Location detected: **{detected_loc}**")
                else:
                    st.warning("📍 Location not detected yet.")
            with loc_col2:
                import modules.geolocation as geolocation
                st.button("📍 Detect Location", width="stretch", type="secondary",
                          key="signup_geo_btn", on_click=geolocation.request_location_fetch)
                if st.session_state.get("_geo_fetch_requested"):
                    st.caption("⏳ Requesting GPS... allow the prompt.")
            
            st.divider()

            # --- SIGNUP FORM ---
            with st.form("signup_form"):
                new_user = st.text_input("Desired Username")
                new_email = st.text_input("Email Address")
                new_pass = st.text_input("Password", type="password")
                new_full_name = st.text_input("Full Name")
                new_role = st.selectbox("I am a...", ["CITIZEN", "EXPERT"])
                
                final_loc_input = st.text_input("Home Location (LGA)", value=detected_loc if detected_loc else "", help="Auto-filled if you clicked 'Detect Location'. You can also type it manually.")
                
                signup_btn = st.form_submit_button("Create Account", width='stretch', type="primary")
                
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
