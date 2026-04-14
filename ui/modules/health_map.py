import streamlit as st
import folium
from folium import plugins
from streamlit_folium import st_folium
import api_client

LAGOS_LGAS = {
    "Agege": {"lat": 6.6179, "lon": 3.3244},
    "Ajeromi-Ifelodun": {"lat": 6.4555, "lon": 3.3641},
    "Alimosho": {"lat": 6.6106, "lon": 3.2958},
    "Amuwo-Odofin": {"lat": 6.4208, "lon": 3.2728},
    "Apapa": {"lat": 6.4349, "lon": 3.3626},
    "Badagry": {"lat": 6.4316, "lon": 2.8876},
    "Epe": {"lat": 6.5841, "lon": 3.9754},
    "Eti-Osa": {"lat": 6.4407, "lon": 3.5412},
    "Ibeju-Lekki": {"lat": 6.4854, "lon": 3.8239},
    "Ifako-Ijaiye": {"lat": 6.6850, "lon": 3.2885},
    "Ikeja": {"lat": 6.6018, "lon": 3.3515},
    "Ikorodu": {"lat": 6.6191, "lon": 3.5041},
    "Kosofe": {"lat": 6.5916, "lon": 3.4177},
    "Lagos Island": {"lat": 6.4549, "lon": 3.4246},
    "Lagos Mainland": {"lat": 6.5059, "lon": 3.3776},
    "Mushin": {"lat": 6.5273, "lon": 3.3554},
    "Ojo": {"lat": 6.4639, "lon": 3.1653},
    "Oshodi-Isolo": {"lat": 6.5372, "lon": 3.3318},
    "Shomolu": {"lat": 6.5392, "lon": 3.3842},
    "Surulere": {"lat": 6.4977, "lon": 3.3525}
}

RISK_WEIGHT = {"Critical": 80, "High": 55, "Moderate": 30, "Low": 12}
COLOR_MAP = {"Critical": "red", "High": "orange", "Moderate": "yellow", "Low": "green",
             "Normal": "green", "Warning": "orange"}

def _match_lga(location_text: str):
    if not location_text:
        return None, None
    for lga, coords in LAGOS_LGAS.items():
        if lga.lower() in location_text.lower() or location_text.lower() in lga.lower():
            return lga, coords
    return None, None


def render():
    st.title("🗺️ Lagos Health Interactive Map")
    st.caption("Live outbreak signal visualisation — powered by real EBS alert data.")
    
    # --- Browser Geolocation (auto-center on user) ---
    user_lat = st.session_state.get("user_lat")
    user_lon = st.session_state.get("user_lon")
    user_loc = st.session_state.get("user_location")
    
    if user_lat and user_lon:
        st.success(f"📍 Map centered on your location: **{user_loc or 'Detected'}**")

    # Fetch live alerts
    alerts = api_client.get_alerts()
    live_data = isinstance(alerts, list) and len(alerts) > 0

    col1, col2, col3 = st.columns(3)
    with col1:
        view_mode = st.selectbox("Layer Logic", ["Disease Outbreaks", "Risk Heatmap", "All Monitored Zones"])
    with col2:
        lga_filter = st.multiselect("Filter LGA", list(LAGOS_LGAS.keys()))
    with col3:
        if live_data:
            active_lgas = set()
            for a in alerts:
                lga, _ = _match_lga(a.get("location_text", ""))
                if lga:
                    active_lgas.add(lga)
            st.metric("Active Signal Zones", len(active_lgas), delta=f"{len(alerts)} signals")
        else:
            st.metric("Active Zones", "No live data yet")

    map_data = []

    # Deferred via @st.fragment — map builds lazily so page shell renders instantly
    @st.fragment
    def _render_map():
        nonlocal map_data
        
        # Build LGA alert buckets (used by all view modes)
        lga_buckets = {}
        if live_data:
            for a in alerts:
                lga, coords = _match_lga(a.get("location_text", ""))
                if not lga:
                    continue
                if lga not in lga_buckets:
                    lga_buckets[lga] = {"coords": coords, "alerts": []}
                lga_buckets[lga]["alerts"].append(a)

        if view_mode == "All Monitored Zones":
            # Show ALL 20 LGAs regardless of alert status
            for lga, coords in LAGOS_LGAS.items():
                if lga_filter and lga not in lga_filter:
                    continue
                
                if lga in lga_buckets:
                    bucket_alerts = lga_buckets[lga]["alerts"]
                    risk_priorities = ["Critical", "High", "Moderate", "Low"]
                    risk_levels = [a.get("risk_level", "Low") for a in bucket_alerts]
                    top_risk = next((r for r in risk_priorities if r in risk_levels), "Low")
                    diseases = ", ".join(set(a.get("disease", "Unknown") for a in bucket_alerts if a.get("disease")))
                    map_data.append({
                        "LGA": lga,
                        "lat": coords["lat"],
                        "lon": coords["lon"],
                        "Value": RISK_WEIGHT.get(top_risk, 12) + (len(bucket_alerts) * 3),
                        "Status": top_risk,
                        "Signals": len(bucket_alerts),
                        "Diseases": diseases or "General Health"
                    })
                else:
                    # No alerts — show as green/nominal
                    map_data.append({
                        "LGA": lga, "lat": coords["lat"], "lon": coords["lon"],
                        "Value": 8, "Status": "Normal", "Signals": 0, "Diseases": "No active signals"
                    })
            
            st.success(f"📡 Showing all **{len(map_data)}** monitored zones across Lagos State.")
        
        elif live_data:
            for lga, bucket in lga_buckets.items():
                if lga_filter and lga not in lga_filter:
                    continue
                coords = bucket["coords"]
                bucket_alerts = bucket["alerts"]
                # Use highest risk level present
                risk_priorities = ["Critical", "High", "Moderate", "Low"]
                risk_levels = [a.get("risk_level", "Low") for a in bucket_alerts]
                top_risk = next((r for r in risk_priorities if r in risk_levels), "Low")
                diseases = ", ".join(set(a.get("disease", "Unknown") for a in bucket_alerts if a.get("disease")))
                map_data.append({
                    "LGA": lga,
                    "lat": coords["lat"],
                    "lon": coords["lon"],
                    "Value": RISK_WEIGHT.get(top_risk, 12) + (len(bucket_alerts) * 3),
                    "Status": top_risk,
                    "Signals": len(bucket_alerts),
                    "Diseases": diseases or "General Health"
                })
        else:
            st.info("🛰️ No live signals yet — agents are scanning. Map will populate automatically.")
            # Still render an empty Lagos-centred map
            for lga, coords in LAGOS_LGAS.items():
                if lga_filter and lga not in lga_filter:
                    continue
                map_data.append({
                    "LGA": lga, "lat": coords["lat"], "lon": coords["lon"],
                    "Value": 5, "Status": "Normal", "Signals": 0, "Diseases": "-"
                })

        if not map_data:
            st.warning("No LGAs match the current filter.")
            return

        # Determine map center: Priority 1: LGA Filter, Priority 2: User Location, Priority 3: Default Lagos
        if lga_filter and lga_filter[0] in LAGOS_LGAS:
            first_lga_coords = LAGOS_LGAS[lga_filter[0]]
            center_lat, center_lon = first_lga_coords["lat"], first_lga_coords["lon"]
            map_zoom = 13
        elif user_lat and user_lon:
            center_lat, center_lon = user_lat, user_lon
            map_zoom = 12
        else:
            center_lat, center_lon = 6.5244, 3.3792
            map_zoom = 10

        m = folium.Map(location=[center_lat, center_lon], zoom_start=map_zoom, tiles="CartoDB positron")
        plugins.Fullscreen().add_to(m)

        if user_lat and user_lon:
            folium.Marker(
                [user_lat, user_lon],
                popup=f"📍 You ({user_loc or 'Your Location'})",
                tooltip="Your Location",
                icon=folium.Icon(color="blue", icon="user")
            ).add_to(m)

        for item in map_data:
            color = COLOR_MAP.get(item["Status"], "green")
            # Scale radius for folium display natively
            radius = max((item["Value"] / 3) + 4, 6)
            
            # HTML Popup content
            html_content = f"<b>{item['LGA']}</b><br/>" \
                           f"Risk Level: {item['Status']}<br/>" \
                           f"Active Signals: {item['Signals']}<br/>" \
                           f"Identified Pathogens: {item['Diseases']}"
                           
            folium.CircleMarker(
                location=[item["lat"], item["lon"]],
                radius=radius,
                color=color,
                weight=1,
                fill=True,
                fill_color=color,
                fill_opacity=0.6,
                tooltip=f"{item['LGA']} - {item['Status']}",
                popup=folium.Popup(html_content, max_width=350)
            ).add_to(m)

        # Render folium map into Streamlit gracefully
        st_folium(m, use_container_width=True, height=650, returned_objects=[])

        if live_data:
            st.success(f"✅ Map rendered from **{len(alerts)} live EBS signals** across {len(map_data)} LGAs.")
        st.info("💡 **Tip:** Hover over circles for signal details. Circle size = signal intensity.")
    
    _render_map()
