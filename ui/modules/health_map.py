import streamlit as st
import pandas as pd
import plotly.express as px
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
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from components.geolocation import render_location_picker
        render_location_picker()
    except Exception:
        pass

    # Fetch live alerts
    alerts = api_client.get_alerts()
    live_data = isinstance(alerts, list) and len(alerts) > 0

    col1, col2, col3 = st.columns(3)
    with col1:
        view_mode = st.selectbox("Layer Logic", ["Disease Outbreaks", "Risk Heatmap"])
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

    if live_data:
        # Aggregate alerts by LGA
        lga_buckets = {}
        for a in alerts:
            lga, coords = _match_lga(a.get("location_text", ""))
            if not lga:
                continue
            if lga not in lga_buckets:
                lga_buckets[lga] = {"coords": coords, "alerts": []}
            lga_buckets[lga]["alerts"].append(a)

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

    df_map = pd.DataFrame(map_data)
    if df_map.empty:
        st.warning("No LGAs match the current filter.")
        return

    fig = px.scatter_mapbox(
        df_map,
        lat="lat", lon="lon",
        hover_name="LGA",
        hover_data={"Value": False, "Status": True, "Signals": True, "Diseases": True},
        color="Status",
        color_discrete_map=COLOR_MAP,
        size="Value",
        size_max=45,
        zoom=9.5,
        height=600,
        mapbox_style="carto-darkmatter"
    )
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    st.plotly_chart(fig, width='stretch')

    if live_data:
        st.success(f"✅ Map rendered from **{len(alerts)} live EBS signals** across {len(map_data)} LGAs.")
    st.info("💡 **Tip:** Hover over circles for signal details. Circle size = signal intensity.")
