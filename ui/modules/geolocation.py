import streamlit as st
import requests
import logging
import json

logger = logging.getLogger(__name__)

# --- DEFINITIVE LAGOS LGA REGISTRY: Instant local geocoding for all 20 LGAs ---
LAGOS_LGA_REGISTRY = {
    "agege": (6.6358, 3.3242),
    "ajeromi-ifelodun": (6.4566, 3.3323),
    "alimosho": (6.6025, 3.2949),
    "amuwo-odofin": (6.4526, 3.2844),
    "apapa": (6.4449, 3.3523),
    "badagry": (6.4173, 2.8833),
    "epe": (6.5794, 3.9822),
    "eti-osa": (6.4463, 3.5350),
    "ibeju-lekki": (6.4950, 4.0200),
    "ifako-ijaiye": (6.6800, 3.3000),
    "ikeja": (6.5965, 3.3420),
    "ikorodu": (6.6194, 3.5105),
    "kosofe": (6.5772, 3.3915),
    "lagos island": (6.4550, 3.3942),
    "lagos mainland": (6.4944, 3.3667),
    "mushin": (6.5294, 3.3486),
    "ojo": (6.4674, 3.1894),
    "oshodi-isolo": (6.5273, 3.3214),
    "shomolu": (6.5367, 3.3853),
    "somolu": (6.5367, 3.3853),
    "surulere": (6.4975, 3.3475),
}


# ─── Browser Geolocation via streamlit-js-eval ──────────────────────────
# This replaces the old st.html() JS injection approach.
# streamlit-js-eval returns data directly to Python — no URL hacking,
# no page reloads, no server-side IP confusion.

def _extract_coords_from_payload(geo_payload) -> tuple:
    """
    Safely extracts (lat, lon) from the streamlit-js-eval geolocation payload.
    Returns (lat, lon, error_string).
    """
    if geo_payload is None:
        return None, None, ""
    
    try:
        # Handle string payloads (some browsers return JSON string)
        if isinstance(geo_payload, str):
            geo_payload = json.loads(geo_payload)
        
        if not isinstance(geo_payload, dict):
            return None, None, "Unexpected payload format"
        
        # Check for errors first
        if "error" in geo_payload:
            return None, None, str(geo_payload["error"])
        if "code" in geo_payload and "message" in geo_payload:
            return None, None, str(geo_payload.get("message", "Permission denied"))
        
        # Try top-level lat/lon
        lat = geo_payload.get("latitude")
        lon = geo_payload.get("longitude")
        if lat is not None and lon is not None:
            return float(lat), float(lon), ""
        
        # Try nested coords object (standard Geolocation API structure)
        coords = geo_payload.get("coords", {})
        if isinstance(coords, dict):
            lat = coords.get("latitude")
            lon = coords.get("longitude")
            if lat is not None and lon is not None:
                return float(lat), float(lon), ""
        
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        return None, None, str(e)
    
    return None, None, "No coordinates in payload"


def inject_geolocation_js():
    """
    Button-triggered geolocation using streamlit-js-eval.
    Replaces the old auto-firing st.html() injection.
    
    This is called once in app.py — it checks if a geolocation request
    was triggered and processes the result.
    """
    # Only process if a fetch was requested via button click
    if not st.session_state.get("_geo_fetch_requested"):
        return
    
    try:
        from streamlit_js_eval import get_geolocation
        payload = get_geolocation(component_key="adiphas_device_geo")
        
        if payload is not None:
            lat, lon, error = _extract_coords_from_payload(payload)
            
            if lat is not None and lon is not None:
                st.session_state.user_lat = lat
                st.session_state.user_lon = lon
                st.session_state._geo_fetch_requested = False
                st.session_state._geo_resolved = True
                logger.info(f"[Geolocation] Browser GPS resolved: ({lat}, {lon})")
                
                # Reverse geocode the coordinates
                loc_string = _reverse_geocode_nominatim(str(lat), str(lon))
                if not loc_string:
                    loc_string = _reverse_geocode_bigdatacloud(str(lat), str(lon))
                if not loc_string:
                    loc_string = _nearest_area_name(lat, lon)
                
                st.session_state.user_location = loc_string
                logger.info(f"[Geolocation] Resolved location: {loc_string}")
            elif error:
                logger.warning(f"[Geolocation] Browser denied: {error}")
                st.session_state._geo_fetch_requested = False
                # Fall back to IP geolocation
                _try_ip_fallback()
    except ImportError:
        logger.warning("[Geolocation] streamlit-js-eval not installed, falling back to IP")
        st.session_state._geo_fetch_requested = False
        _try_ip_fallback()
    except Exception as e:
        logger.warning(f"[Geolocation] JS eval error: {e}")
        st.session_state._geo_fetch_requested = False


def request_location_fetch():
    """Call this from a button's on_click to trigger geolocation."""
    st.session_state._geo_fetch_requested = True


def _try_ip_fallback():
    """Attempts IP-based geolocation as a fallback."""
    if st.session_state.get("_ip_geo_attempted"):
        return
    st.session_state._ip_geo_attempted = True
    ip_loc = _geolocate_by_ip()
    if ip_loc and "Unknown" not in ip_loc:
        st.session_state.user_location = ip_loc
        logger.info(f"[Geolocation] IP fallback resolved: {ip_loc}")


def _nearest_area_name(lat: float, lon: float) -> str:
    """Returns the nearest Lagos area name via Euclidean distance."""
    best_name = "Lagos"
    best_dist = float("inf")
    for name, (a_lat, a_lon) in LAGOS_LGA_REGISTRY.items():
        dist = ((lat - a_lat) ** 2 + (lon - a_lon) ** 2) ** 0.5
        if dist < best_dist:
            best_dist = dist
            best_name = name.title()
    return best_name


def _forward_geocode_nominatim(query: str) -> tuple[float, float] | None:
    """Converts a location string (e.g. 'Yaba, Lagos') into coordinates."""
    if not query:
        return None
        
    # Phase 0: Instant Local Registry Lookup (High-Reliability Fallback)
    clean_q = query.lower().replace("lga", "").replace("local government", "").replace(", lagos", "").replace(", nigeria", "").strip()
    if clean_q in LAGOS_LGA_REGISTRY:
        logger.info(f"[Geolocation] Instant Registry matched: {clean_q}")
        return LAGOS_LGA_REGISTRY[clean_q]
        
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
    Main geolocation orchestrator. Reads coordinates from session state
    (populated by streamlit-js-eval or IP fallback), performs reverse
    geolocation, and returns a formatted location string.
    
    Resilience chain:
    1. Browser GPS via streamlit-js-eval → reverse geocode
    2. IP-based geolocation via ipapi.co / ip-api.com
    3. User profile location_lga (last resort)
    """
    # If we already have a valid location cached, return it
    cached_loc = st.session_state.get("user_location")
    if cached_loc and "Unknown" not in cached_loc:
        return cached_loc
    
    # Nuke corrupted "Unknown Area" cache to allow the engine to retry
    if cached_loc and "Unknown Area" in cached_loc:
        st.session_state.user_location = None
        st.session_state._ip_geo_attempted = False
    
    # Check if we have coordinates from GPS or IP
    lat = st.session_state.get("user_lat")
    lon = st.session_state.get("user_lon")
    
    if lat and lon:
        # Reverse geocode the coordinates
        loc_string = _reverse_geocode_nominatim(str(lat), str(lon))
        if not loc_string:
            loc_string = _reverse_geocode_bigdatacloud(str(lat), str(lon))
        if not loc_string:
            loc_string = _nearest_area_name(float(lat), float(lon))
        
        st.session_state.user_location = loc_string
        return loc_string
    
    # Try IP-based fallback
    if not st.session_state.get("_ip_geo_attempted"):
        _try_ip_fallback()
        if st.session_state.get("user_location"):
            return st.session_state.user_location
    
    # Last resort: user profile location
    if st.session_state.get("authenticated") and st.session_state.get("user"):
        profile_loc = st.session_state.user.get("location_lga")
        if profile_loc and "Unknown" not in str(profile_loc):
            st.session_state.user_location = profile_loc
            # Geocode the profile location string if coords are missing
            if not st.session_state.get("user_lat"):
                coords = _forward_geocode_nominatim(profile_loc)
                if coords:
                    st.session_state.user_lat, st.session_state.user_lon = coords
            return profile_loc
    
    return None
