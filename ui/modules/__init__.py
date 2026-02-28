import streamlit as st

def render_footer():
    """Renders the mandatory medical disclaimer footer."""
    footer_color = "#94a3b8"
    
    st.markdown(
        f"""
        <div style='text-align: center; color: {footer_color}; font-size: 0.8rem; padding: 20px 0;'>
            <p><strong>⚠️ ADIPHAS Critical Enforcement Disclaimer</strong></p>
            <p>ADIPHAS is an advisory support tool and does not provide medical diagnoses. 
            Consult a clinician for professional evaluation.</p>
        </div>
        """, 
        unsafe_allow_html=True
    )

