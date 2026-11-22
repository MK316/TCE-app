
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
import base64
import re

# ------------------------------------------
# Page configuration
# ------------------------------------------
st.set_page_config(
    page_title="Exam Practice",
    page_icon="📘",
    layout="wide"
)

st.title("English Teacher Certification Exam")
st.caption("Select an exam year and practice the questions.")

# ------------------------------------------
# File paths
# ------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
YEARS_DIR = BASE_DIR / "years"

# Find available exam years
available_years = sorted(
    [
        folder.name
        for folder in YEARS_DIR.iterdir()
        if folder.is_dir()
        and folder.name.isdigit()
        and (folder / "index.html").exists()
    ],
    reverse=True
) if YEARS_DIR.exists() else []

if not available_years:
    st.warning("No exam questions are available yet.")
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

# Embed local images as Base64
def embed_image(match):
    prefix, relative_path, suffix = match.groups()

    image_path = html_path.parent / relative_path

    if not image_path.is_file():
        return match.group(0)

    extension = image_path.suffix.lower()

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif"
    }

    mime = mime_types.get(extension)

    if mime is None:
        return match.group(0)

    encoded = base64.b64encode(
        image_path.read_bytes()
    ).decode("ascii")

    return (
        prefix
        + f"data:{mime};base64,{encoded}"
        + suffix
    )

# Replace image paths used in the HTML
html_content = re.sub(
    r'(\bimage:\s*["\'])(images/[^"\']+)(["\'])',
    embed_image,
    html_content
)

# ------------------------------------------
# Display exam HTML
# ------------------------------------------
components.html(
    html_content,
    height=1250,
    scrolling=True
)
