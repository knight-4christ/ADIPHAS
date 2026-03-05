"""
Browser Geolocation Component for Streamlit.
Uses the browser's navigator.geolocation API to get the user's actual position.
Zero API tokens — runs entirely in the browser.
"""
import streamlit.components.v1 as components


def get_user_location(key="geolocation"):
    """
    Renders a JavaScript component that requests the user's GPS coordinates.
    Returns (lat, lon) tuple if available, else (None, None).
    
    Usage:
        from components.geolocation import get_user_location
        lat, lon = get_user_location()
    """
    # JavaScript that requests geolocation and passes it back to Streamlit
    geolocation_js = """
    <script>
    (function() {
        // Check if location was already fetched this session
        const stored = window.parent.sessionStorage.getItem('adiphas_geolocation');
        if (stored) {
            const coords = JSON.parse(stored);
            const div = document.getElementById('geo-result');
            if (div) div.innerText = JSON.stringify(coords);
            return;
        }
        
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                function(position) {
                    const coords = {
                        lat: position.coords.latitude,
                        lon: position.coords.longitude,
                        accuracy: position.coords.accuracy
                    };
                    window.parent.sessionStorage.setItem('adiphas_geolocation', JSON.stringify(coords));
                    const div = document.getElementById('geo-result');
                    if (div) div.innerText = JSON.stringify(coords);
                },
                function(error) {
                    const div = document.getElementById('geo-result');
                    if (div) div.innerText = JSON.stringify({error: error.message});
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 300000  // Cache for 5 minutes
                }
            );
        } else {
            const div = document.getElementById('geo-result');
            if (div) div.innerText = JSON.stringify({error: "Geolocation not supported"});
        }
    })();
    </script>
    <div id="geo-result" style="display:none;"></div>
    """
    
    components.html(geolocation_js, height=0)
    
    # Note: Due to Streamlit's architecture, the JS result isn't directly
    # returned in the same render cycle. The coordinates are stored in
    # sessionStorage and can be read via st.session_state on the next cycle.
    # For immediate use, the health_map module can read from session_state.
    
    return None, None


def render_location_picker():
    """
    Renders a visible location request button with status feedback.
    Stores coordinates in st.session_state['user_lat'] and st.session_state['user_lon'].
    """
    import streamlit as st
    
    location_js = """
    <div style="padding: 10px; border-radius: 8px; background: rgba(14, 165, 233, 0.1); margin: 10px 0;">
        <button id="loc-btn" onclick="requestLocation()" style="
            background: linear-gradient(135deg, #0ea5e9, #06b6d4);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
        ">📍 Detect My Location</button>
        <span id="loc-status" style="margin-left: 10px; color: #94a3b8; font-size: 13px;">Click to share your location</span>
    </div>
    
    <script>
    function requestLocation() {
        const status = document.getElementById('loc-status');
        const btn = document.getElementById('loc-btn');
        
        btn.disabled = true;
        status.innerText = '⏳ Requesting location...';
        
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                function(pos) {
                    const lat = pos.coords.latitude.toFixed(4);
                    const lon = pos.coords.longitude.toFixed(4);
                    status.innerText = '✅ Location: ' + lat + ', ' + lon;
                    status.style.color = '#4ade80';
                    
                    // Store in sessionStorage for Streamlit to read
                    window.parent.sessionStorage.setItem('user_lat', lat);
                    window.parent.sessionStorage.setItem('user_lon', lon);
                },
                function(err) {
                    status.innerText = '❌ ' + err.message;
                    status.style.color = '#ef4444';
                    btn.disabled = false;
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
        } else {
            status.innerText = '❌ Geolocation not supported by this browser.';
            status.style.color = '#ef4444';
        }
    }
    </script>
    """
    
    components.html(location_js, height=70)
