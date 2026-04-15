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
                            const city = (data.city || "").toLowerCase();
                            // FATAL ROUTE GUARD: Reject server-side locations (Render/Streamlit Cloud)
                            if (city.includes("dallas") || city.includes("dalles") || city.includes("boardman") || city.includes("oregon")) {
                                console.warn("Rejected server-side IP location, falling back to profile.");
                                url.searchParams.set('geo_denied', '1');
                            } else {
                                url.searchParams.set('lat', data.latitude.toFixed(4));
                                url.searchParams.set('lon', data.longitude.toFixed(4));
                                url.searchParams.set('ip_loc', data.city + ", " + data.region);
                            }
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
    
def _forward_geocode_nominatim(query: str) -> tuple[float, float] | None:
    """Converts a location string (e.g. 'Yaba, Lagos') into coordinates."""
    if not query:
        return None
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={query}, Nigeria&format=json&limit=1"
        headers = {"User-Agent": "ADIPHAS_Health_App/1.0"}
        response = requests.get(url, headers=headers, timeout=4)
        if response.status_code == 200:
            data = response.json()
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        logger.warning(f"[Geolocation] Forward geocoding failed for {query}: {e}")
    return None

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
            headers = st.context.headers
            # Check multiple standard proxy headers
            header_keys = ["X-Forwarded-For", "X-Real-Ip", "True-Client-Ip", "X-Appengine-User-Ip"]
            for key in header_keys:
                header_val = headers.get(key)
                if header_val:
                    for ip in header_val.split(","):
                        ip = ip.strip()
                        # Ignore common private/reserved subnets
                        if not (ip.startswith("10.") or ip.startswith("192.168.") or ip.startswith("127.") or ip.startswith("172.")):
                            client_ip = ip
                            break
                if client_ip:
                    break
        
        # FATAL GUARD: If no public client IP is extracted, ABORT!
        # Do not allow it to query `https://ipapi.co/json/` natively, because that will resolve to the Streamlit Server in Oregon!
        if not client_ip:
            logger.warning("[Geolocation] Blocked Streamlit from assigning Server IP (Oregon). Aborting IP geolocator.")
            return None
                
        api_url = f"https://ipapi.co/{client_ip}/json/"
        response = requests.get(api_url, timeout=5, headers={"User-Agent": "ADIPHAS/1.0"})
        if response.status_code == 200:
            data = response.json()
            
            # API might return {"error": true} for unresolvable IPs
            if data.get("error"):
                logger.warning(f"[Geolocation] IPAPI error: {data.get('reason')}")
                return None
                
            city = data.get("city")
            region = data.get("region")
            lat_ip = data.get("latitude")
            lon_ip = data.get("longitude")
            
            # Reject garbage or server-side payloads (The Dalles, Dallas, Oregon)
            if not city or not region or any(x in city.lower() or x in region.lower() for x in ["oregon", "dalles", "dallas", "boardman"]):
                return None
            
            # Store IP-derived coordinates as backup
            if lat_ip and lon_ip:
                st.session_state.user_lat = float(lat_ip)
                st.session_state.user_lon = float(lon_ip)
            
            return f"{city}, {region}"
    except Exception as e:
        logger.warning(f"[Geolocation] IPAPI fallback failed: {e}")
        
    # --- REDUNDANT FALLBACK: ip-api.com (Free, Open Source API) ---
    try:
        url = "http://ip-api.com/json/?fields=status,message,country,regionName,city,lat,lon"
        response = requests.get(url, timeout=4)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                city = data.get("city")
                region = data.get("regionName")
                lat_ip = data.get("lat")
                lon_ip = data.get("lon")
                
                # Reject server-side locations
                if city and any(x in city.lower() for x in ["oregon", "dalles", "dallas", "boardman"]):
                    return None
                    
                if lat_ip and lon_ip:
                    st.session_state.user_lat = float(lat_ip)
                    st.session_state.user_lon = float(lon_ip)
                return f"{city}, {region}"
    except Exception as e:
        logger.warning(f"[Geolocation] IP-API fallback failed: {e}")
        
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
    ip_loc_param = st.query_params.get("ip_loc")
    
    # Nuke corrupted "Unknown Area" cache to allow the engine to retry
    curr_loc = st.session_state.get("user_location")
    if curr_loc and "Unknown Area" in curr_loc:
        st.session_state.user_location = None
        st.session_state._ip_geo_attempted = False
        
    # --- Path 0: JS Client IP Fallback Succeeded ---
    if ip_loc_param:
        st.session_state.user_location = ip_loc_param
        if lat and lon:
            st.session_state.user_lat = float(lat)
            st.session_state.user_lon = float(lon)
        return ip_loc_param
    
    # --- Path A: Browser geolocation was denied → use server IP fallback ---
    if geo_denied and not lat:
        if not st.session_state.get("_ip_geo_attempted"):
            st.session_state._ip_geo_attempted = True
            ip_loc = _geolocate_by_ip()
            if ip_loc and "Unknown Area" not in ip_loc:
                st.session_state.user_location = ip_loc
                logger.info(f"[Geolocation] IP-based fallback resolved: {ip_loc}")
                return ip_loc
        
        # Skip stale or server-side cached locations
        cached = st.session_state.get("user_location")
        if cached and not any(x in str(cached).lower() for x in ["oregon", "dalles", "unknown"]):
            # If we have a valid city string but NO coordinates, continue to profile geocoding
            if st.session_state.get("user_lat") and st.session_state.get("user_lon"):
                return cached
        
        # Last resort: user profile location
        if st.session_state.get("authenticated") and st.session_state.get("user"):
            profile_loc = st.session_state.user.get("location_lga")
            if profile_loc and not any(x in str(profile_loc).lower() for x in ["oregon", "dalles", "unknown"]):
                st.session_state.user_location = profile_loc
                # Geocode the profile location string if coords are missing or still at Oregon
                if not st.session_state.get("user_lat") or not st.session_state.get("user_lon"):
                    coords = _forward_geocode_nominatim(profile_loc)
                    if coords:
                        st.session_state.user_lat, st.session_state.user_lon = coords
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
