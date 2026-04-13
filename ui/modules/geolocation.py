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
    Always checks for fresh coordinates — re-geocodes if coords changed or cache is stale (>5 min).
    """
    import time
    
    lat = st.query_params.get("lat")
    lon = st.query_params.get("lon")
    
    if not lat or not lon:
        # No coordinates in URL — return whatever we have cached, or None
        return st.session_state.get("user_location")
    
    # Check if coordinates have changed or cache is stale
    cached_lat = st.session_state.get("_geo_cached_lat")
    cached_lon = st.session_state.get("_geo_cached_lon")
    cached_time = st.session_state.get("_geo_cached_time", 0)
    
    coords_changed = (str(cached_lat) != str(lat)) or (str(cached_lon) != str(lon))
    cache_stale = (time.time() - cached_time) > 300  # 5 minutes
    
    if not coords_changed and not cache_stale and st.session_state.get("user_location"):
        # Coordinates same and cache fresh — use cached result
        return st.session_state.get("user_location")
    
    # Coordinates changed or cache expired — re-geocode
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
            
            # Update cache tracking
            st.session_state._geo_cached_lat = lat
            st.session_state._geo_cached_lon = lon
            st.session_state._geo_cached_time = time.time()
            
            return loc_string
    except Exception as e:
        st.session_state.user_location = f"Lat: {str(lat)[:6]}, Lon: {str(lon)[:6]}"
        st.session_state.user_lat = float(lat)
        st.session_state.user_lon = float(lon)
        st.session_state._geo_cached_lat = lat
        st.session_state._geo_cached_lon = lon
        st.session_state._geo_cached_time = time.time()
        return st.session_state.user_location
        
    return st.session_state.get("user_location")

