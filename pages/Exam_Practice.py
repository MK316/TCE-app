"""Streamlit page for yearly teacher-certification exam HTML apps.

Put this file in the Streamlit app's ``pages/`` directory, and keep the
``years/`` folder at the repository root (beside app.py).
"""
from pathlib import Path
import re
import base64

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="중등영어 임용 기출 연습", page_icon="📘", layout="wide")
st.title("중등영어 임용 기출 연습")
st.caption("연도를 선택한 후, 해당 연도 문항을 풀이하고 자동 피드백을 확인하세요.")

# pages/Exam_Practice.py -> repository root
ROOT = Path(__file__).resolve().parents[1]
YEARS_DIR = ROOT / "years"

available = sorted(
    (p.name for p in YEARS_DIR.iterdir()
     if p.is_dir() and re.fullmatch(r"20\d{2}", p.name)
     and (p / "index.html").is_file()),
    reverse=True,
) if YEARS_DIR.is_dir() else []

if not available:
    st.error("연도별 HTML 파일을 찾지 못했습니다. years/2026/index.html 경로를 확인하세요.")
    st.stop()

year = st.selectbox("연도 선택", available, index=0)
# Optional question dropdown in Streamlit; inside the HTML there are matching tabs.
question = st.selectbox("문항 선택", ["2026-1", "2026-2", "2026-3"] if year == "2026" else ["전체 문항"], index=0)

html_path = YEARS_DIR / year / "index.html"
html_text = html_path.read_text(encoding="utf-8")

# Embed source images as data URIs so they work in Streamlit's HTML iframe.
for image_index in range(1, 4):
    token = f"images/2026-{image_index}.webp"
    image_file = html_path.parent / "images" / f"2026-{image_index}.webp"
    if token in html_text and image_file.is_file():
        encoded = base64.b64encode(image_file.read_bytes()).decode("ascii")
        html_text = html_text.replace(token, f"data:image/webp;base64,{encoded}")

# Change the initial question in each year's single-file app without JS injection.
# The HTML app defaults to question 1, or reads ?q= / #q= if hosted directly.
# In Streamlit components.html, inject a scoped initial-selection statement.
if year == "2026":
    index = int(question.rsplit("-", 1)[1]) - 1
    html_text = html_text.replace(
        "// Optional parent embedding can specify #q=2 or ?q=2 to select a problem.",
        f"selectQuestion({index});\n// Optional parent embedding can specify #q=2 or ?q=2 to select a problem.",
    )
    # The final URL-selection statement is harmless for default q=1, but can
    # override the injected selection. Replace it to preserve Streamlit choice.
    html_text = html_text.replace(
        "selectQuestion(Number.isInteger(n)&&n>=1&&n<=3?n-1:0);",
        f"selectQuestion({index});",
    )

components.html(html_text, height=1120, scrolling=True)
