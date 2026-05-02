"""
Browser Geolocation Component for Streamlit.
Uses streamlit-js-eval for reliable browser geolocation.
Zero API tokens — runs entirely in the browser.
"""
import streamlit as st


def get_user_location(key="geolocation"):
    """
    Requests the user's GPS coordinates via streamlit-js-eval.
    Returns (lat, lon) tuple if available, else (None, None).
    
    Usage:
        from components.geolocation import get_user_location
        lat, lon = get_user_location()
    """
    try:
        from streamlit_js_eval import get_geolocation
        import json
        
        payload = get_geolocation(component_key=key)
        
        if payload is None:
            return None, None
        
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        if isinstance(payload, dict):
            # Try nested coords
            coords = payload.get("coords", payload)
            lat = coords.get("latitude")
            lon = coords.get("longitude")
            if lat is not None and lon is not None:
                return float(lat), float(lon)
    except ImportError:
        st.warning("📍 Geolocation requires `streamlit-js-eval`. Install it with: `pip install streamlit-js-eval`")
    except Exception:
        pass
    
    return None, None


def render_location_picker():
    """
    Renders a visible location request button with status feedback.
    Stores coordinates in st.session_state['user_lat'] and st.session_state['user_lon'].
    """
    from modules.geolocation import request_location_fetch
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        if st.session_state.get("user_lat") and st.session_state.get("user_lon"):
            st.success(f"📍 Location detected: ({st.session_state.user_lat:.4f}, {st.session_state.user_lon:.4f})")
        else:
            st.info("📍 Click the button to detect your location")
    
    with col2:
        st.button("📍 Detect", key="loc_picker_btn", on_click=request_location_fetch, type="primary")
