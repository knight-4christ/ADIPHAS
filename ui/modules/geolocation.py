import streamlit as st
import streamlit.components.v1 as components
import requests
import logging

logger = logging.getLogger(__name__)

def inject_geolocation_js():
    """
    Injects a hidden HTML block with JS that reads navigator.geolocation
    and pushes the values into Streamlit's URL search parameters.
    Coordinates are rounded to 4 decimal places (~11m) to prevent GPS drift loops.
    """
    js_code = """
    <script>
    if ("geolocation" in navigator) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const lat = position.coords.latitude.toFixed(4);
                const lon = position.coords.longitude.toFixed(4);
                
                const url = new URL(window.parent.location.href);
                const currentLat = url.searchParams.get('lat');
                const currentLon = url.searchParams.get('lon');
                
                // Only push if coordinates differ (rounded to prevent drift loops)
                if (currentLat !== lat || currentLon !== lon) {
                    url.searchParams.set('lat', lat);
                    url.searchParams.set('lon', lon);
                    window.parent.location.search = url.search;
                }
            },
            (error) => {
                console.warn("Geolocation denied, engaging Client IP fallback...");
                fetch('https://ipapi.co/json/')
                    .then(r => r.json())
                    .then(data => {
                        const url = new URL(window.parent.location.href);
                        if (data.latitude && data.longitude) {
                            url.searchParams.set('lat', data.latitude.toFixed(4));
                            url.searchParams.set('lon', data.longitude.toFixed(4));
                            url.searchParams.set('ip_loc', data.city + ", " + data.region);
                            window.parent.location.search = url.search;
                        } else {
                            if (!url.searchParams.has('geo_denied')) {
                                url.searchParams.set('geo_denied', '1');
                                window.parent.location.search = url.search;
                            }
                        }
                    })
                    .catch(e => {
                        const url = new URL(window.parent.location.href);
                        if (!url.searchParams.has('geo_denied')) {
                            url.searchParams.set('geo_denied', '1');
                            window.parent.location.search = url.search;
                        }
                    });
            },
            { enableHighAccuracy: true, timeout: 8000, maximumAge: 300000 }
        );
    }
    </script>
    """
    st.html(js_code)

def _reverse_geocode_nominatim(lat: str, lon: str) -> str | None:
    """Primary reverse geocoder using OpenStreetMap Nominatim."""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=10"
        headers = {"User-Agent": "ADIPHAS_Health_App/1.0"}
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            data = response.json()
            address = data.get("address", {})
            # Prioritize granular suburbs/neighborhoods for accurate Lagos clustering
            local_area = address.get("suburb") or address.get("neighbourhood") or address.get("county") or address.get("city") or address.get("town") or "Unknown Area"
            state = address.get("state") or "Unknown State"
            return f"{local_area}, {state}"
    except Exception as e:
        logger.warning(f"[Geolocation] Nominatim failed: {e}")
    return None

def _reverse_geocode_bigdatacloud(lat: str, lon: str) -> str | None:
    """Fallback reverse geocoder using BigDataCloud (free, no API key)."""
    try:
        url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=en"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            city = data.get("city") or data.get("locality") or "Unknown Area"
            state = data.get("principalSubdivision") or "Unknown State"
            return f"{city}, {state}"
    except Exception as e:
        logger.warning(f"[Geolocation] BigDataCloud failed: {e}")
    return None

def _geolocate_by_ip() -> str | None:
    """IP-based geolocation fallback using ipapi.co (free, no API key)."""
    try:
        # Securely extract the true Client IP traversing through the Streamlit Cloud Proxies
        client_ip = ""
        if hasattr(st, "context"):
            forwarded = st.context.headers.get("X-Forwarded-For")
            if forwarded:
                # X-Forwarded-For can be a comma separated list, first is the originating client IP
                client_ip = forwarded.split(",")[0].strip()
                
        api_url = f"https://ipapi.co/{client_ip}/json/" if client_ip else "https://ipapi.co/json/"
        response = requests.get(api_url, timeout=3, headers={"User-Agent": "ADIPHAS/1.0"})
        if response.status_code == 200:
            data = response.json()
            city = data.get("city") or "Unknown Area"
            region = data.get("region") or "Unknown State"
            lat_ip = data.get("latitude")
            lon_ip = data.get("longitude")
            
            # Store IP-derived coordinates as backup
            if lat_ip and lon_ip:
                st.session_state.user_lat = float(lat_ip)
                st.session_state.user_lon = float(lon_ip)
            
            return f"{city}, {region}"
    except Exception as e:
        logger.warning(f"[Geolocation] IP fallback failed: {e}")
    return None


def extract_and_geocode():
    """
    Reads coordinates from query params, performs reverse geolocation via
    multi-provider chain (Nominatim → BigDataCloud → IP-based), and returns
    a formatted location string (e.g. "Lagos Mainland, Lagos").
    
    Resilience chain:
    1. Browser GPS → Nominatim reverse geocode
    2. Browser GPS → BigDataCloud reverse geocode (fallback)
    3. IP-based geolocation via ipapi.co (if browser denied)
    4. User profile location_lga (last resort)
    """
    import time
    
    lat = st.query_params.get("lat")
    lon = st.query_params.get("lon")
    geo_denied = st.query_params.get("geo_denied")
    
    # --- Path A: Browser geolocation was denied → use IP fallback ---
    if geo_denied and not lat:
        if not st.session_state.get("_ip_geo_attempted"):
            st.session_state._ip_geo_attempted = True
            ip_loc = _geolocate_by_ip()
            if ip_loc:
                st.session_state.user_location = ip_loc
                logger.info(f"[Geolocation] IP-based fallback resolved: {ip_loc}")
                return ip_loc
        
        # Already attempted IP — use cached or profile fallback
        cached = st.session_state.get("user_location")
        if cached:
            return cached
        
        # Last resort: user profile location
        if st.session_state.get("authenticated") and st.session_state.get("user"):
            profile_loc = st.session_state.user.get("location_lga")
            if profile_loc:
                st.session_state.user_location = profile_loc
                return profile_loc
        
        return None
    
    # --- Path B: No coordinates yet (still loading) ---
    if not lat or not lon:
        return st.session_state.get("user_location")
    
    # --- Path C: Coordinates available → reverse geocode ---
    # Check cache freshness (avoid re-geocoding on every rerun)
    cached_lat = st.session_state.get("_geo_cached_lat")
    cached_lon = st.session_state.get("_geo_cached_lon")
    cached_time = st.session_state.get("_geo_cached_time", 0)
    
    coords_changed = (str(cached_lat) != str(lat)) or (str(cached_lon) != str(lon))
    cache_stale = (time.time() - cached_time) > 300  # 5 minutes
    
    if not coords_changed and not cache_stale and st.session_state.get("user_location"):
        return st.session_state.get("user_location")
    
    # Multi-provider reverse geocoding chain
    loc_string = _reverse_geocode_nominatim(lat, lon)
    
    if not loc_string:
        loc_string = _reverse_geocode_bigdatacloud(lat, lon)
    
    if not loc_string:
        # Raw coordinate fallback
        loc_string = f"Lat: {str(lat)[:7]}, Lon: {str(lon)[:7]}"
    
    # Store results
    st.session_state.user_location = loc_string
    st.session_state.user_lat = float(lat)
    st.session_state.user_lon = float(lon)
    st.session_state._geo_cached_lat = lat
    st.session_state._geo_cached_lon = lon
    st.session_state._geo_cached_time = time.time()
    
    return loc_string
