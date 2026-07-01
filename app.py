import streamlit as st
from pathlib import Path

st.set_page_config(page_title="널스빌리지 콘텐츠 뷰어", page_icon="🩺", layout="wide")

ROOT = Path(__file__).parent

PAGES = {
    "전체보기 (통합본)": ROOT / "output" / "전체보기.md",
    "Basic 제출물 (output_content_set.md)": ROOT / "output" / "output_content_set.md",
    "발행 캘린더 (rescheduled-calendar.md)": ROOT / "output" / "rescheduled-calendar.md",
    "브랜드보이스 가이드 (standard-guide.md)": ROOT / "output" / "standard-guide.md",
    "파이프라인 사용법 (pipeline-usage.md)": ROOT / "output" / "pipeline-usage.md",
    "콘텐츠 템플릿 (template.md)": ROOT / "output" / "template.md",
    "의사결정 로그 (decisions.md)": ROOT / "decisions.md",
}

st.sidebar.title("🩺 널스빌리지 콘텐츠")
choice = st.sidebar.radio("문서 선택", list(PAGES.keys()))

path = PAGES[choice]
st.title(choice)

if path.exists():
    st.markdown(path.read_text(encoding="utf-8"))
else:
    st.warning(f"파일을 찾을 수 없습니다: {path}")
