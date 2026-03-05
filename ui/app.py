import streamlit as st
import api_client
from datetime import datetime
from dotenv import load_dotenv
import os
load_dotenv()  # Loads .env for UI process (e.g. GEMINI_API_KEY for chat)

# Import new modules
from modules import (
    auth, home, local_feed, idsr_analytics, 
    ebs_alerts, health_map, personal_alerts, 
    health_profile, admin, chat, evaluation
)

# --- GLOBAL DATA FETCH (Cached at Top Level) ---
@st.cache_data(ttl=20, show_spinner="Gathering health intelligence...")
def fetch_global_alerts():
    return api_client.get_alerts()

@st.cache_data(ttl=20)
def get_ui_counts(alerts, last_check, user_lga, authenticated):
    """Calculates counts for unread sidebar notifications (Cached)."""
    if not isinstance(alerts, list):
        return {"total": 0, "personal": 0, "pending": 0}
    
    # Only count alerts newer than the last time we viewed the feed
    new_alerts = [a for a in alerts if a.get("created_at", "") > last_check]
    
    total_new = len(new_alerts)
    personal_new = len([a for a in new_alerts if a.get("location_text") == user_lga]) if user_lga and authenticated else 0
    pending_new = len([a for a in alerts if not a.get("verified")])
    
    return {
        "total": total_new, "personal": personal_new, "pending": pending_new
    }

# --- NATIVE OVERLAY FUNCTION ---
@st.dialog("🤖 ADIPHAS Advisory Chat", width="large")
def show_chat_overlay():
    chat.render(is_overlay=True)

def main():
    st.set_page_config(
        page_title="ADIPHAS - Autonomous Intelligence",
        page_icon="ui/assets/icon_surveillance.png", 
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # --- SESSION STATE & PERSISTENCE ---
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.user = None
        st.session_state.token = None
        
        # Try persistence via query params (Memory across refreshes)
        q_token = st.query_params.get("session_token")
        if q_token:
            with st.spinner("Restoring session..."):
                me = api_client.get_me(q_token)
                if me and "username" in me:
                    st.session_state.authenticated = True
                    st.session_state.token = q_token
                    st.session_state.user = me
    
    # Permanently Dark Mode (Launchpad Aesthetic)
    st.session_state.theme_mode = "Dark"

    if "last_checked_alerts" not in st.session_state:
        st.session_state.last_checked_alerts = "1970-01-01T00:00:00"

    # Fetch alerts once per session rerun (or from cache)
    all_alerts = fetch_global_alerts()
    st.session_state["cached_alerts"] = all_alerts
    
    last_check = st.session_state.get("last_checked_alerts", "1970-01-01T00:00:00")
    user_lga = st.session_state.user.get("location_lga") if st.session_state.authenticated else None
    
    counts = get_ui_counts(all_alerts, last_check, user_lga, st.session_state.authenticated)
    
    # --- THEME CONFIGURATION (Launchpad Inspired) ---
    bg_color = "#0B1111"      # Deep Dark Slate
    text_color = "#E2E8F0"    # Light Grey
    secondary_text = "#94A3B8"
    sidebar_bg = "#1C3C3C"    # Launchpad Dark Teal
    card_bg = "#162222"       # Slightly lighter for cards
    
    # --- GLOBAL STYLING ---
    st.markdown(f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap');
        
        * {{ font-family: 'Inter', sans-serif; }}
        
        /* Main Container */
        .main {{
            background-color: {bg_color};
            color: {text_color};
        }}
        
        /* Sidebar Styling */
        [data-testid="stSidebar"] {{
            background-color: {sidebar_bg};
            border-right: 1px solid #334155;
        }}
        [data-testid="stSidebar"] img {{
            mix-blend-mode: screen; /* Effectively removes black backgrounds */
        }}
        h2 {{
            font-family: 'Outfit', sans-serif;
            letter-spacing: 2px;
            font-weight: 800;
        }}
        
        /* Text Contrast for native elements */
        .stMarkdown, .stCaption, p, li {{
            color: {text_color} !important;
        }}
        
        [data-testid="stCaptionContainer"] {{
            color: {secondary_text} !important;
        }}
        
        /* Headers */
        h1, h2, h3 {{
            color: #0ea5e9 !important; /* Sky 500 */
            font-weight: 600;
        }}
        
        /* Metric Cards */
        [data-testid="stMetricValue"] {{
            color: #f59e0b !important; /* Amber 500 */
        }}
        [data-testid="stMetricLabel"] {{
            color: {secondary_text} !important;
        }}

        /* Simplified Cards */
        div[data-testid="stVerticalBlock"] > div {{
            background-color: transparent;
            border-radius: 0px;
            padding: 10px;
            border: none;
            box-shadow: none;
            margin-bottom: 5px;
        }}
        
        /* Custom Buttons */
        div.stButton > button {{
            background-color: #0ea5e9;
            color: white !important;
            border-radius: 8px;
            border: none;
            padding: 0.6rem 1.2rem;
            font-weight: 600;
        }}
        
        /* Form Inputs */
        .stTextInput > div > div > input {{
            background-color: #334155;
            color: {text_color} !important;
            border: 1px solid #475569;
            border-radius: 6px;
        }}
        </style>
    """, unsafe_allow_html=True)

    # --- SIDEBAR & NAVIGATION ---
    with st.sidebar:
        # Display Branding Logo (Combined with text for a 'text-based' feel)
        col_logo, col_text = st.columns([1, 4])
        with col_logo:
            try:
                st.image("ui/assets/logo.png", width=45)
            except:
                st.write("🛡️")
        with col_text:
            st.markdown("<h2 style='margin-top: -5px; color: #00f2ff;'>ADIPHAS</h2>", unsafe_allow_html=True)
        
        st.caption("Autonomous Disease Intelligence")
        
        # Theme toggle removed (Persistent Dark)
        
        # --- NAVIGATION CATEGORIES ---
        auth_status = st.session_state.authenticated
        user_role = st.session_state.user.get("role", "CITIZEN") if auth_status else "GUEST"
        
        # Define Categories and their Modules
        categories = {
            "Surveillance": ["Command Centre", "Local Health Feed", "Interactive Map"],
            "Intelligence": ["Health Intel Inbox", "Advisory Chat"],
            "Analytics": ["IDSR Analytics", "System Evaluation"],
            "Account": ["My Profile", "User Management"]
        }
        
        # Adjust based on role
        if user_role == "GUEST":
            categories = {
                "Surveillance": ["Command Centre", "Local Health Feed", "Login / Sign Up"],
            }
        elif user_role == "CITIZEN":
            categories["Intelligence"] = ["Health Intel Inbox", "Advisory Chat"]
            categories["Surveillance"] = ["Local Health Feed", "Command Centre", "Interactive Map"]
            if "Analytics" in categories: del categories["Analytics"]
            if "User Management" in categories["Account"]: categories["Account"].remove("User Management")
        else: # EXPERT or ADMIN
            categories["Intelligence"] = ["Health Intel Inbox", "EBS Verification", "Advisory Chat"]
            categories["Surveillance"] = ["Local Health Feed", "Command Centre", "Interactive Map"]
            if user_role == "EXPERT":
                if "User Management" in categories["Account"]: categories["Account"].remove("User Management")
            if user_role == "ADMIN":
                if "My Profile" in categories["Account"]: categories["Account"].remove("My Profile")

        # Category Selection
        cat_list = list(categories.keys())
        if "active_nav_cat" not in st.session_state or st.session_state.active_nav_cat not in cat_list:
            st.session_state.active_nav_cat = cat_list[0]
            
        cat_index = cat_list.index(st.session_state.active_nav_cat)
        cat_choice = st.selectbox(
            "Select Area", 
            cat_list, 
            index=cat_index,
            key=f"nav_cat_sb_{user_role}"
        )
        st.session_state.active_nav_cat = cat_choice

        # Display Section Icon
        icon_map = {
            "Surveillance": "ui/assets/icon_surveillance.png",
            "Intelligence": "ui/assets/icon_intelligence.png",
            "Analytics": "ui/assets/icon_analytics.png"
        }
        if cat_choice in icon_map:
            try:
                st.image(icon_map[cat_choice], width=40)
            except:
                pass
        
        # Menu Selection within category
        menu_options = categories[cat_choice]
        if "active_nav_mod" not in st.session_state or st.session_state.active_nav_mod not in menu_options:
            st.session_state.active_nav_mod = menu_options[0]
            
        mod_index = menu_options.index(st.session_state.active_nav_mod)
        
        def format_nav(label):
            if label == "Health Intel Inbox" or label == "Local Health Feed":
                return f"{label} ({counts['total']})" if counts.get('total', 0) > 0 else label
            if label == "EBS Verification":
                return f"{label} ({counts['pending']})" if counts.get('pending', 0) > 0 else label
            return label
            
        choice = st.radio(
            "Module", 
            menu_options, 
            index=mod_index,
            format_func=format_nav, 
            label_visibility="collapsed", 
            key=f"nav_mod_rd_{user_role}"
        )
        st.session_state.active_nav_mod = choice
        
        if auth_status:
            # User profile widget
            st.divider()
            st.write(f"👤 **{st.session_state.user['username']}**")
            st.caption(f"Role: {user_role} | ID: {st.session_state.user.get('id', 'Unknown')[:8]}")
            st.divider()
            
            if st.button("Logout", key="logout_btn", use_container_width=True):
                st.query_params.clear()
                auth.logout()
        else:
            st.info("🔐 Login to access personal alerts and maps.")
            
    # --- MAIN CONTENT ROUTING ---
    
    # Global Feedback Banner (Persistent across reruns)
    if "success_banner" in st.session_state and st.session_state.success_banner:
        st.success(f"✅ {st.session_state.success_banner}")
        st.session_state.success_banner = None # Clear after display
    
    # Check Auth for Protected Routes
    protected_routes_prefixes = [
        "Health Intel Inbox", "IDSR Analytics", "EBS Verification", 
        "My Profile", "User Management", "System Evaluation"
    ]
    
    is_protected = any(choice.startswith(prefix) for prefix in protected_routes_prefixes)
    
    if is_protected and not st.session_state.authenticated:
        st.warning("⚠️ Access Restricted. Please Login.")
        auth.render_login_modal()
        st.stop()

    # Module Router (Using startswith because labels now have counts)
    if choice == "Command Centre":
        home.render()
        
    elif choice.startswith("Local Health Feed"):
        local_feed.render()
        
    elif choice == "Login / Sign Up":
        auth.render_login_modal()
        
    elif choice == "Advisory Chat":
        chat.render()
        
    elif choice == "Interactive Map":
        health_map.render()
        
    elif choice.startswith("Health Intel Inbox"):
        personal_alerts.render()
        
    elif choice == "IDSR Analytics":
        idsr_analytics.render()
        
    elif choice.startswith("EBS Verification"):
        ebs_alerts.render()
        
    elif choice == "My Profile":
        health_profile.render()
        
    elif choice == "System Evaluation":
        evaluation.render()
        
    elif choice == "User Management":
        admin.render()
        
    # --- FLOATING ADVISORY CHAT ICON ---
    # Show on all pages EXCEPT when already in the main Advisory Chat page
    if choice != "Advisory Chat":
        st.markdown("""
            <style>
            /* Flawless CSS injection to target the Streamlit button container without breaking click events */
            div[data-testid="stElementContainer"]:has(#fab-hook) + div[data-testid="stElementContainer"] {
                position: fixed !important;
                top: 75px !important;  /* Moved down slightly per request */
                right: 40px !important;
                z-index: 99999 !important;
                width: auto !important;
                background: transparent !important;
            }
            div[data-testid="stElementContainer"]:has(#fab-hook) + div[data-testid="stElementContainer"] button {
                background-color: #0ea5e9 !important;
                color: white !important;
                border-radius: 50% !important;
                width: 65px !important;
                height: 65px !important;
                font-size: 30px !important;
                box-shadow: 0 4px 15px rgba(0,0,0,0.6) !important;
                border: 2px solid #38bdf8 !important;
                transition: transform 0.2s ease, background-color 0.2s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                line-height: normal !important;
                padding: 0 !important;
            }
            div[data-testid="stElementContainer"]:has(#fab-hook) + div[data-testid="stElementContainer"] button > div {
                margin: 0 !important;
                padding: 0 !important;
            }
            div[data-testid="stElementContainer"]:has(#fab-hook) + div[data-testid="stElementContainer"] button:hover {
                transform: scale(1.1) !important;
                background-color: #0284c7 !important;
            }
            </style>
            <div id="fab-hook" style="display: none;"></div>
        """, unsafe_allow_html=True)
        
        if st.button("💬", key="fab_chat", help="Open Advisory Chat Overlay"):
            if st.session_state.authenticated:
                show_chat_overlay()
            else:
                st.warning("Please login to access the Advisory Chat.")
                st.session_state.active_nav_cat = "Surveillance"
                st.session_state.active_nav_mod = "Login / Sign Up"
                st.rerun()

    from modules import render_footer
    render_footer()

if __name__ == "__main__":
    main()
