"""Power plant risk model - Streamlit web application (Bahasa Indonesia).

Run:  streamlit run streamlit_app.py
"""
import streamlit as st

st.set_page_config(page_title="Model Risiko Pembangkit", page_icon="⚡", layout="wide")

from app_lib import ui  # noqa: E402

ui.inject_css()
pages = [
    st.Page("app_pages/1_data.py", title="1. Data", icon=":material/upload_file:", default=True),
    st.Page("app_pages/2_build.py", title="2. Bangun model", icon=":material/tune:"),
    st.Page("app_pages/3_validation.py", title="3. Validasi model", icon=":material/fact_check:"),
    st.Page("app_pages/4_dashboard.py", title="4. Dasbor", icon=":material/monitoring:"),
    st.Page("app_pages/5_resume.py", title="5. Ringkasan model", icon=":material/summarize:"),
]
nav = st.navigation(pages)
ui.sidebar_status()
nav.run()
