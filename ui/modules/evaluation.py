import streamlit as st
import api_client
import json
import pandas as pd
from datetime import datetime

def render():
    st.title("🔬 NLP Evaluation & Scientific Rigor")
    st.caption("Measure and audit the performance of ADIPHAS Analyst Agents.")

    tab1, tab2, tab3 = st.tabs(["📊 Performance Metrics", "✍️ Manual Annotation", "📜 History"])

    with tab1:
        st.subheader("Global NLP Metrics")
        metrics = api_client.get_evaluation_metrics()
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Average F1-Score", f"{metrics.get('avg_f1', 0.0):.4f}")
        with col2:
            st.metric("Total Samples", metrics.get("total_samples", 0))

        st.info("💡 F1-Score is a harmonic mean of Precision and Recall. A score above 0.8 is considered publication-grade for prototype health intelligence systems.")

        # Confusion Matrix Logic (Derived from existing samples)
        samples = api_client.get_evaluation_samples()
        if samples:
            st.subheader("Confusion Matrix Component")
            # In a real implementation, we'd aggregate TP, FP, FN across all samples.
            # For this UI, we show a summary table.
            df = pd.DataFrame(samples)
            st.dataframe(df[['id', 'f1_score', 'created_at']].head(10), width='stretch')

    with tab2:
        st.subheader("New Annotation Sample")
        st.write("Extract entities from a raw text snippet to evaluate system performance.")
        
        raw_text = st.text_area("Raw Health Intelligence Text", placeholder="Ex: Reports of Cholera outbreak in Alimosho LGA yesterday...")
        
        if st.button("1. Run ADIPHAS Extraction"):
            if not raw_text:
                st.error("Please enter text first.")
            else:
                with st.spinner("Agent analyzing..."):
                    # Fixed: Use API call instead of direct backend import
                    # (enables proper UI/backend separation in containerised deployment)
                    result = api_client.nlp_extract(raw_text)
                    if result.get("error"):
                        st.error(f"Extraction failed: {result.get('detail')}")
                    else:
                        entities = result.get("entities", {})
                        st.session_state.actual_eval = entities
                        st.success("Extraction Complete (System Insight)")
                        st.json(entities)

        if "actual_eval" in st.session_state:
            st.divider()
            st.markdown("### 🧬 Ground Truth Annotation")
            st.write("Select what the system *should* have found:")
            
            # Use predefined lists for consistency
            DISEASES = ["Cholera", "Malaria", "Lassa Fever", "Measles", "Meningitis", "Typhoid"]
            LGAS = [
                "Agege", "Ajeromi-Ifelodun", "Alimosho", "Amuwo-Odofin", "Apapa", "Badagry",
                "Epe", "Eti-Osa", "Ibeju-Lekki", "Ifako-Ijaiye", "Ikeja", "Ikorodu",
                "Kosofe", "Lagos Island", "Lagos Mainland", "Mushin", "Ojo", "Oshodi-Isolo",
                "Shomolu", "Surulere"
            ]

            expected_diseases = st.multiselect("Expected Diseases", DISEASES)
            expected_locations = st.multiselect("Expected Locations (LGAs)", LGAS)

            if st.button("2. Submit To Evaluation Engine"):
                expected = {"diseases": expected_diseases, "locations": expected_locations}
                actual = st.session_state.actual_eval
                
                payload = {
                    "raw_text": raw_text,
                    "expected_entities": json.dumps(expected),
                    "actual_entities": json.dumps(actual)
                }
                
                res = api_client.submit_evaluation(payload)
                if res:
                    st.success(f"Evaluation Submitted! Sample F1-Score: {res.get('f1_score', 0.0):.4f}")
                    del st.session_state.actual_eval
                    st.rerun()

    with tab3:
        st.subheader("Audit Trail")
        samples = api_client.get_evaluation_samples()
        if samples:
            for s in samples:
                with st.expander(f"Sample #{s['id']} - F1: {s['f1_score']:.4f} ({s['created_at'][:19]})"):
                    st.write("**Raw Text:**")
                    st.text(s['raw_text'])
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Expected (Ground Truth):**")
                        st.json(json.loads(s['expected_entities']))
                    with c2:
                        st.markdown("**Actual (System Output):**")
                        st.json(json.loads(s['actual_entities']))
        else:
            st.write("No evaluation history found.")
