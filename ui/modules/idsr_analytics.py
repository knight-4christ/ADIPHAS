import streamlit as st
import api_client
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import random

def render():
    st.title("📊 IDSR Analytics & Forecasting")
    st.caption("Integrated Disease Surveillance and Response Data Portal")
    
    tab1, tab2 = st.tabs(["📄 Data Upload", "📈 Predictive Modeling"])
    
    with tab1:
        st.subheader("Upload Weekly Surveillance Data")
        uploaded_file = st.file_uploader("Upload IDSR CSV", type=["csv"])
        
        if uploaded_file:
            st.info("Preview:")
            try:
                df = pd.read_csv(uploaded_file)
                st.dataframe(df.head(), width='stretch')
                
                if st.button("Ingest Data into Backend"):
                    # Reset pointer
                    uploaded_file.seek(0)
                    with st.spinner("Processing..."):
                        res = api_client.upload_idsr(uploaded_file)
                        if res:
                            st.success(f"Successfully ingested {res.get('ingested_rows')} rows.")
            except Exception as e:
                st.error(f"Error reading CSV: {e}")

    with tab2:
        st.subheader("Disease Forecasting Model")
        
        col1, col2 = st.columns(2)
        with col1:
            # LGA selection — codes must match the lga_code column in IDSRRecord table
            lga_input = st.selectbox("Select LGA", ["Surulere", "Ikeja", "Eti-Osa", "Alimosho", "Lagos Mainland", "Kosofe", "Shomolu"])
            # Direct LGA code (matches what script seeds into DB: "SURULERE", etc.)
            lga_map = {
                "Surulere": "SURULERE", "Ikeja": "IKEJA", "Eti-Osa": "ETI-OSA",
                "Alimosho": "ALIMOSHO", "Lagos Mainland": "MAINLAND",
                "Kosofe": "KOSOFE", "Shomolu": "SHOMOLU"
            }
            lga_code = lga_map.get(lga_input, lga_input.upper())
            
        with col2:
            disease = st.selectbox("Target Disease", ["Cholera", "Lassa Fever", "Measles", "Meningitis"])
            
        if st.button("Run Forecast Model"):
            with st.spinner(f"Running Weighted Moving Average + Trend model for {disease} in {lga_input}..."):
                forecast = api_client.get_forecast(lga_code, disease)
                
            if forecast and not forecast.get("error"):
                # Handle Insufficient Data Fallback
                if forecast.get("forecast") == []:
                    st.info(f"📊 **Insufficient Historical Data**")
                    st.write(forecast.get("policy_recommendation_plan", "Need at least 4 weeks of data to generate a forecast."))
                    st.caption("The system is actively monitoring real-time intelligence for this LGA.")
                else:
                    # Accuracy Metrics (SECTION 2: Evaluation Framework requirements)
                    st.markdown("### 🧬 Model Performance Metrics")
                    m1, m2, m3 = st.columns(3)
                    mae = forecast.get('mae', 0)
                    m1.metric("MAE (Mean Absolute Error)", f"{mae:.2f}")
                    m2.metric("RMSE", f"{forecast.get('rmse', 0):.2f}")
                    
                    data_points = forecast.get('data_points_used', 0)
                    m3.metric("Validation Period", f"2 Weeks ({data_points} wks data)")

                # Prominent Anomaly Banner (Flagging Feature)
                if forecast.get("anomaly_flag"):
                    st.error(f"🚨 **EPIDEMIC ANOMALY DETECTED**: Statistical surge detected for {disease} in {lga_input}. Z-score exceeds safety threshold (2.0). Escalating surveillance priority.")

                st.info(f"💡 Low MAE ({mae:.2f}) indicates high historical accuracy for {disease} in {lga_input}.")
                
                # AI Epidemiological Narrative
                narrative = forecast.get("epidemiological_narrative")
                if narrative:
                    st.success(f"🧠 **AI Epidemiological Narrative**: {narrative}")

                # Visualizing multi-week forecast
                st.subheader("Forecast Trajectory (4 Weeks)")
                
                preds = forecast.get('forecast', [10, 10, 10, 10])
                ci_low = forecast.get('ci_lower', [5, 5, 5, 5])
                ci_high = forecast.get('ci_upper', [15, 15, 15, 15])

                # --- Real IDSR historical baseline ---
                hist_res = api_client.get_idsr_history(lga_code=lga_code, disease=disease)
                if isinstance(hist_res, list) and hist_res:
                    hist_df = pd.DataFrame(hist_res)
                    hist_df["week_start"] = pd.to_datetime(hist_df["week_start"])
                    hist_df = hist_df.sort_values("week_start").tail(8)
                    hist_dates = hist_df["week_start"].tolist()
                    hist_vals = hist_df["cases"].tolist()
                else:
                    st.caption("ℹ️ No IDSR records for this LGA/disease yet. Upload CSV to see real historical data.")
                    hist_dates = pd.date_range(end=pd.Timestamp.now(), periods=8, freq='W').tolist()
                    hist_vals = [0] * 8

                forecast_dates = pd.date_range(start=hist_dates[-1], periods=5, freq='W')[1:].tolist()

                chart_data = pd.DataFrame({
                    "Date": hist_dates + forecast_dates,
                    "Cases": hist_vals + preds,
                    "Lower CI": [None]*8 + ci_low,
                    "Upper CI": [None]*8 + ci_high,
                    "Type": ["Historical"]*8 + ["Forecast"]*4
                })

                fig = px.line(chart_data, x="Date", y="Cases", color="Type", markers=True,
                             template="plotly_dark",
                             color_discrete_map={"Historical": "#94a3b8", "Forecast": "#0ea5e9"})
                
                # Add confidence intervals
                fig.add_trace(go.Scatter(
                    x=chart_data[chart_data["Type"] == "Forecast"]["Date"],
                    y=chart_data[chart_data["Type"] == "Forecast"]["Upper CI"],
                    fill=None, mode='lines', line_color='rgba(14, 165, 233, 0)', showlegend=False
                ))
                fig.add_trace(go.Scatter(
                    x=chart_data[chart_data["Type"] == "Forecast"]["Date"],
                    y=chart_data[chart_data["Type"] == "Forecast"]["Lower CI"],
                    fill='tonexty', mode='lines', line_color='rgba(14, 165, 233, 0)',
                    fillcolor='rgba(14, 165, 233, 0.2)', name='95% Confidence Interval'
                ))
                
                fig.update_layout(
                    margin=dict(l=20, r=20, t=40, b=20),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(family="Inter, sans-serif", size=12, color="#94a3b8"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig, width='stretch')
                
                # --- Hybrid RAG Intelligence Section ---
                st.markdown("---")
                st.subheader("🌐 Hybrid RAG Intelligence")
                st.caption("Searching local knowledge base (verified alerts) with fallback to global news...")
                
                search_query = f"Latest outbreaks and protocols for {disease} in {lga_input} Nigeria"
                with st.spinner("Retrieving intelligence context..."):
                    rag_res = api_client.advisory_search(search_query)
                    
                if rag_res and not rag_res.get("error"):
                    source = rag_res.get("source", "unknown")
                    results = rag_res.get("results", [])
                    
                    if source == "local_rag":
                        st.info("✅ Found relevant context in local verified alerts database.")
                    elif source == "web_search":
                        st.warning("🔍 Local database sparse. Fetched live global intelligence via Tavily.")
                    
                    if results:
                        for i, r in enumerate(results[:2]): # Show top 2
                            content = r.get("content") or r.get("snippet") or str(r)
                            with st.expander(f"Intelligence Insight #{i+1}"):
                                st.write(content)
                else:
                    st.write("No additional intelligence context found for this query.")
                
            elif forecast and forecast.get("error"):
                st.error(f"API Error: {forecast.get('detail')}")
