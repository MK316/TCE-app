
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
import base64
import re

# ------------------------------------------
# Page configuration
# ------------------------------------------
st.set_page_config(
    page_title="English Teacher Certification Exam",
    page_icon="📘",
    layout="wide"
)

st.title("English Teacher Certification Exam")
st.caption("Select an exam year and practice the questions.")

# ------------------------------------------
# File paths
# ------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
YEARS_DIR = ROOT / "years"

# Find available exam years
available_years = sorted(
    [
        folder.name
        for folder in YEARS_DIR.iterdir()
        if (
            folder.is_dir()
            and re.fullmatch(r"20\d{2}", folder.name)
            and (folder / "index.html").is_file()
        )
    ],
    reverse=True
) if YEARS_DIR.exists() else []

if not available_years:
    st.warning("No exam questions are available.")
    st.stop()

# ------------------------------------------
# Year selection only
# ------------------------------------------
selected_year = st.selectbox(
    "Select Exam Year",
    available_years
)

# ------------------------------------------
# Load HTML
# ------------------------------------------
html_path = YEARS_DIR / selected_year / "index.html"
html_content = html_path.read_text(encoding="utf-8")

# ------------------------------------------
# Embed local images
# ------------------------------------------
mime_types = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif"
}

# Match image paths within HTML or JavaScript
image_pattern = re.compile(
    r"(['\"])(images/[^'\"]+\.(?:png|jpg|jpeg|webp|gif))\1",
    re.IGNORECASE
)

def embed_image(match):
    quote, relative_path = match.groups()

    image_path = html_path.parent / relative_path

    if not image_path.is_file():
        return match.group(0)

    extension = image_path.suffix.lower()
    mime = mime_types.get(extension)

    if mime is None:
        return match.group(0)

    encoded = base64.b64encode(
        image_path.read_bytes()
    ).decode("ascii")

    return (
        f"{quote}data:{mime};base64,{encoded}{quote}"
    )

# Replace image paths with embedded image data
html_content = image_pattern.sub(
    embed_image,
    html_content
)

# ------------------------------------------
# Display exam application
# ------------------------------------------
components.html(
    html_content,
    height=1250,
    scrolling=True
)
