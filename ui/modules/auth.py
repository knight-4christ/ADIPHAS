import streamlit as st
import api_client
import time

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
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.subheader("🔐 Access ADIPHAS")
        
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
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
                                    st.success(f"Welcome back, {me['username']}!")
                                    time.sleep(0.5)
                                    st.rerun()
                                else:
                                    st.error("Failed to load profile.")
                            else:
                                st.error("Invalid credentials.")
        
        with tab2:
            with st.form("signup_form"):
                new_user = st.text_input("Desired Username")
                new_email = st.text_input("Email Address")
                new_pass = st.text_input("Password", type="password")
                new_full_name = st.text_input("Full Name")
                new_role = st.selectbox("I am a...", ["CITIZEN", "EXPERT"])
                
                signup_btn = st.form_submit_button("Create Account", width='stretch')
                
                if signup_btn:
                    if not new_user or not new_pass or not new_email:
                        st.error("Please fill in all required fields.")
                    else:
                        with st.spinner("Creating account..."):
                            res = api_client.register(new_user, new_pass, new_email, new_full_name, new_role)
                            if "id" in res:
                                st.success("Account created successfully! Please switch to the Login tab.")
                            else:
                                st.error(f"Signup Failed: {res.get('detail', 'Unknown error')}")

def logout():
    """Clears session state and logs the user out."""
    st.session_state.clear()
    st.session_state.authenticated = False
    st.session_state.token = None
    st.session_state.user = None
    st.rerun()
