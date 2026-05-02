import sys
import os
# --- BOOT SHIELD: Force parent directory into sys.path to prevent Streamlit KeyError: 'modules' ---
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import streamlit as st
import api_client
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()  # Loads .env for UI process (e.g. GEMINI_API_KEY for chat)

# Import new modules - Hardened Absolute Package Imports
import modules.auth as auth
import modules.local_feed as local_feed
import modules.idsr_analytics as idsr_analytics
import modules.ebs_alerts as ebs_alerts
import modules.health_map as health_map
import modules.personal_alerts as personal_alerts
import modules.health_profile as health_profile
import modules.admin as admin
import modules.chat as chat
import modules.evaluation as evaluation
import modules.situational_awareness as situational_awareness
import modules.geolocation as geolocation

def is_profile_complete(user: dict) -> bool:
    """Checks if the user has completed all mandatory bio-data fields."""
    required_fields = ['blood_group', 'genotype', 'location_lga', 'health_conditions']
    for field in required_fields:
        value = user.get(field)
        if not value or str(value).strip() == '' or value == 'None':
            return False
    return True

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

def main():
    st.set_page_config(
        page_title="ADIPHAS - Autonomous Intelligence",
        page_icon="ui/assets/icon_surveillance.png", 
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # --- BROWSER GEOLOCATION INTEGRATION ---
    # Process any pending geolocation request (button-triggered, not auto-fire)
    geolocation.inject_geolocation_js()
    current_loc = geolocation.extract_and_geocode()
    
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
        
        /* === MOBILE RESPONSIVE === */
        @media (max-width: 768px) {{
            /* 4-Column Layouts (like the top metrics) become a 2x2 Grid */
            [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(4)) {{
                display: grid !important;
                grid-template-columns: 1fr 1fr !important;
                gap: 10px;
            }}
            [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(4)) > [data-testid="stColumn"] {{
                width: 100% !important;
                min-width: 100% !important;
                padding: 0 !important;
            }}
            
            /* Stack all other columns vertically on mobile */
            [data-testid="stHorizontalBlock"]:not(:has(> [data-testid="stColumn"]:nth-child(4))) {{
                flex-direction: column !important;
            }}
            [data-testid="stHorizontalBlock"]:not(:has(> [data-testid="stColumn"]:nth-child(4))) > [data-testid="stColumn"] {{
                width: 100% !important;
                min-width: 100% !important;
            }}
            
            /* Reduce padding for mobile */
            .main .block-container {{
                padding: 0.5rem 0.8rem !important;
            }}
            
            /* Smaller headings on mobile */
            h1 {{ font-size: 1.4rem !important; }}
            h2 {{ font-size: 1.2rem !important; }}
            h3 {{ font-size: 1.05rem !important; }}
            
            /* Full-width buttons on mobile */
            div.stButton > button {{
                width: 100% !important;
                padding: 0.7rem 1rem !important;
                font-size: 14px !important;
            }}
            
            /* Compact metrics */
            [data-testid="stMetricValue"] {{
                font-size: 1.2rem !important;
            }}
            [data-testid="stMetricLabel"] {{
                font-size: 0.75rem !important;
            }}
            
            /* Sidebar auto-collapse on mobile */
            [data-testid="stSidebar"] {{
                min-width: 200px !important;
                max-width: 260px !important;
            }}
            
            /* Touch-friendly expanders */
            details summary {{
                padding: 12px 8px !important;
                font-size: 14px !important;
            }}
        }}
        
        @media (max-width: 480px) {{
            .main .block-container {{
                padding: 0.3rem 0.5rem !important;
            }}
            h1 {{ font-size: 1.2rem !important; }}
            [data-testid="stMetricValue"] {{
                font-size: 1rem !important;
            }}
        }}
        
        /* === BACK TO TOP BUTTON === */
        #back-to-top {{
            position: fixed;
            bottom: 90px;
            right: 20px;
            z-index: 99998;
            background: linear-gradient(135deg, #0ea5e9, #06b6d4);
            color: white;
            border: 2px solid #38bdf8;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            font-size: 22px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            display: none;
            align-items: center;
            justify-content: center;
            transition: transform 0.2s ease, opacity 0.3s ease;
        }}
        #back-to-top:hover {{
            transform: scale(1.15);
        }}
        </style>
        
        <!-- Back to Top Button -->
        <button id="back-to-top" onclick="window.scrollTo({{top: 0, behavior: 'smooth'}})" title="Back to top">⬆</button>
        <script>
        window.addEventListener('scroll', function() {{
            const btn = document.getElementById('back-to-top');
            if (btn) {{
                if (window.scrollY > 400) {{
                    btn.style.display = 'flex';
                }} else {{
                    btn.style.display = 'none';
                }}
            }}
        }});
        // Also check inside Streamlit's main scrollable container
        const mainSection = document.querySelector('section.main');
        if (mainSection) {{
            mainSection.addEventListener('scroll', function() {{
                const btn = document.getElementById('back-to-top');
                if (btn) {{
                    if (mainSection.scrollTop > 400) {{
                        btn.style.display = 'flex';
                    }} else {{
                        btn.style.display = 'none';
                    }}
                }}
            }});
        }}
        </script>
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
        
        # --- LOCATION RESOLUTION: Try IP/profile fallback for first load ---
        if auth_status:
            if not st.session_state.get("user_location"):
                geolocation.extract_and_geocode()

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
            
            # Determine global location
            profile_loc = st.session_state.user.get('location_lga') or st.session_state.user.get('state')
            detected_loc = st.session_state.get('user_location')
            loc_val = detected_loc if detected_loc else profile_loc
            st.session_state.global_location = loc_val if loc_val else "Unknown Location"
            
            st.caption(f"Role: {user_role} | ID: {st.session_state.user.get('id', 'Unknown')[:8]}")
            
            # Display coordinates alongside location for transparency
            user_lat = st.session_state.get("user_lat")
            user_lon = st.session_state.get("user_lon")
            coord_str = f" [{user_lat}, {user_lon}]" if user_lat and user_lon else ""
            st.caption(f"📍 {st.session_state.global_location}{coord_str}")
            
            # Button-triggered GPS detection (replaces auto-fire injection)
            if not st.session_state.get("_geo_resolved"):
                st.button("📍 Detect My Location", key="sidebar_geo_btn", on_click=geolocation.request_location_fetch, type="secondary")
            st.divider()
            
            if st.button("Logout", key="logout_btn", width="stretch"):
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
    
    # --- MANDATORY BIO-DATA COMPLETION GATE ---
    # Non-admin authenticated users must complete their profile before accessing any module
    if st.session_state.authenticated:
        user_role = st.session_state.user.get("role", "CITIZEN")
        if user_role != "ADMIN" and not is_profile_complete(st.session_state.user):
            st.warning("⚠️ **Profile Incomplete** — Please complete all bio-data fields before accessing other modules.")
            st.info("📝 Blood Group, Genotype, Location (LGA), and Health Conditions are all required for personalized health intelligence.")
            health_profile.render(force_completion=True)
            st.stop()

    # Module Router (Using startswith because labels now have counts)
    if choice == "Command Centre":
        situational_awareness.render()
        
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
        # Check authentication locally for the button trigger
        authenticated = st.session_state.get("authenticated", False)
        
        # JS Injection to forcefully style and float the button
        st.markdown(f"""
            <style>
            div[data-testid="stElementContainer"]:has(#fab-hook) + div[data-testid="stElementContainer"] {{
                position: fixed !important;
                top: 100px !important;
                right: 40px !important;
                z-index: 99999 !important;
                width: auto !important;
                background: transparent !important;
            }}
            div[data-testid="stElementContainer"]:has(#fab-hook) + div[data-testid="stElementContainer"] button {{
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
            }}
            div[data-testid="stElementContainer"]:has(#fab-hook) + div[data-testid="stElementContainer"] button:hover {{
                transform: scale(1.1) !important;
                background-color: #0284c7 !important;
            }}
            </style>
            <div id="fab-hook" style="display: none;"></div>
        """, unsafe_allow_html=True)
        
        def handle_fab_click():
            authenticated = st.session_state.get("authenticated", False)
            if authenticated:
                st.session_state.active_nav_cat = "Intelligence"
                st.session_state.active_nav_mod = "Advisory Chat"
            else:
                st.session_state.active_nav_cat = "Surveillance"
                st.session_state.active_nav_mod = "Login / Sign Up"
                st.session_state["_fab_toast"] = "⚠️ Please login to access the Advisory Chat."

        st.button("💬", key="fab_chat", help="Open Advisory Chat", on_click=handle_fab_click)
        
        # Display the toast if it was set during the callback
        if "_fab_toast" in st.session_state:
            st.toast(st.session_state.pop("_fab_toast"))

    import modules as modules_pkg
    modules_pkg.render_footer()

if __name__ == "__main__":
    main()
