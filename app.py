import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path

st.set_page_config(
    page_title="다이버즈 × 널스빌리지 콘텐츠 대시보드",
    page_icon="🩺",
    layout="wide",
)

DASHBOARD_HTML = (Path(__file__).parent / "output" / "dashboard.html").read_text(encoding="utf-8")

st.markdown(
    """<style>
    .block-container{padding-top:0;padding-bottom:0;max-width:100%;}
    iframe{border:none;display:block;}
    header[data-testid="stHeader"]{display:none;}
    div[data-testid="stToolbar"]{display:none;}
    div[data-testid="stDecoration"]{display:none;}
    #MainMenu{visibility:hidden;}
    footer{visibility:hidden;}
    </style>""",
    unsafe_allow_html=True,
)
components.html(DASHBOARD_HTML, height=2000, scrolling=True)
