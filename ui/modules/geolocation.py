import streamlit as st
import streamlit.components.v1 as components
import requests

def inject_geolocation_js():
    """
    Injects a hidden HTML block with JS that reads navigator.geolocation
    and pushes the values into Streamlit's URL search parameters.
    """
    js_code = """
    <script>
    if ("geolocation" in navigator) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const lat = position.coords.latitude;
                const lon = position.coords.longitude;
                
                const url = new URL(window.parent.location.href);
                const currentLat = url.searchParams.get('lat');
                const currentLon = url.searchParams.get('lon');
                
                // If coordinates aren't in the URL or differ significantly, push them and reload
                if (currentLat !== lat.toString() && currentLon !== lon.toString()) {
                    url.searchParams.set('lat', lat);
                    url.searchParams.set('lon', lon);
                    window.parent.location.search = url.search;
                }
            },
            (error) => {
                console.warn("Geolocation denied or unavailable: ", error);
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }
    </script>
    """
    components.html(js_code, height=0, width=0)

def extract_and_geocode():
    """
    Reads coordinates from query params, performs reverse geolocation via Nominatim OpenStreetMap,
    and returns a formatted location string (e.g. "Lagos Mainland, Lagos").
    Caches the result in session state.
    """
    if "user_location" in st.session_state and st.session_state.user_location:
        return st.session_state.user_location
        
    lat = st.query_params.get("lat")
    lon = st.query_params.get("lon")
    
    if lat and lon:
        try:
            url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=10"
            headers = {"User-Agent": "ADIPHAS_Health_App/1.0"}
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                address = data.get("address", {})
                
                local_area = address.get("city") or address.get("town") or address.get("county") or "Unknown Area"
                state = address.get("state") or "Unknown State"
                
                loc_string = f"{local_area}, {state}"
                st.session_state.user_location = loc_string
                st.session_state.user_lat = float(lat)
                st.session_state.user_lon = float(lon)
                return loc_string
        except Exception as e:
            st.session_state.user_location = f"Lat: {lat[:6]}, Lon: {lon[:6]}"
            return st.session_state.user_location
            
    return None
