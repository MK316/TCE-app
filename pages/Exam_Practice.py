import base64
from pathlib import Path
import re

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="중등영어 임용 기출 연습", page_icon="📘", layout="wide")
st.title("중등영어 임용 기출 연습")
st.caption("연도를 선택한 후, 해당 연도 문항을 풀이하고 자동 피드백을 확인하세요.")

ROOT = Path(__file__).resolve().parents[1]
YEARS_DIR = ROOT / "years"

available = sorted(
    [
        p.name for p in YEARS_DIR.iterdir()
        if p.is_dir() and re.fullmatch(r"20\d{2}", p.name) and (p / "index.html").is_file()
    ],
    reverse=True,
) if YEARS_DIR.is_dir() else []

if not available:
    st.error("연도별 HTML 파일을 찾지 못했습니다. years/2026/index.html 등의 경로를 확인하세요.")
    st.stop()

year = st.selectbox("연도 선택", available, index=0)
html_path = YEARS_DIR / year / "index.html"
html_text = html_path.read_text(encoding="utf-8")

mime_types = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

pattern = re.compile(r'(["'])((?:images/)[^"']+\.(?:png|jpg|jpeg|webp|gif))(["'])', re.IGNORECASE)

def replacer(match):
    quote1, relative_path, quote2 = match.groups()
    image_file = html_path.parent / relative_path
    if not image_file.is_file():
        return match.group(0)
    mime = mime_types.get(image_file.suffix.lower())
    if mime is None:
        return match.group(0)
    encoded = base64.b64encode(image_file.read_bytes()).decode("ascii")
    return f"{quote1}data:{mime};base64,{encoded}{quote2}"

html_text = pattern.sub(replacer, html_text)
components.html(html_text, height=1250, scrolling=True)
