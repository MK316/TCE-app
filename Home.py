"""Stick Figure Teacher's Dream - Streamlit app

Run:  streamlit run app.py
(make_gif.py must be in the same folder; teacher_dream_en.gif is generated automatically if missing)
"""
import base64
from pathlib import Path

import streamlit as st

from make_gif import generate

HERE = Path(__file__).parent
GIF_PATH = HERE / "teacher_dream_en.gif"

st.set_page_config(page_title="Journey to Become a Teacher", page_icon="🍎", layout="centered")


@st.cache_data(show_spinner="Drawing the animation...")
def load_gif_bytes() -> bytes:
    if not GIF_PATH.exists():
        generate(str(GIF_PATH))
    return GIF_PATH.read_bytes()


st.title("🍎 Journey to Become a Teacher")
st.caption("A college student's journey from Year 1 to Year 4 on the way to becoming a teacher")

gif = load_gif_bytes()

# Embedding as base64 keeps the GIF animated in every Streamlit version.
b64 = base64.b64encode(gif).decode()
st.markdown(
    f'<img src="data:image/gif;base64,{b64}" '
    f'style="width:100%;border-radius:12px;border:1px solid #ddd;" alt="Teacher dream animation">',
    unsafe_allow_html=True,
)

with st.expander("📚 The story, year by year"):
    st.markdown(
        """
- **Year 1** · Enters the College of Education and starts with Intro to Education
- **Year 2** · Deep in major courses, studying late into the night
- **Year 3** · Practices mock lessons in front of classmates
- **Year 4** · Student teaching, the teacher certification exam, and... PASS!
- **After graduation** · Finally standing in front of a real classroom 🎉
"""
    )

col1, col2 = st.columns(2)
with col1:
    st.download_button("⬇️ Download GIF", gif, file_name="teacher_dream_en.gif", mime="image/gif")
with col2:
    if st.button("🔄 Rebuild GIF"):
        GIF_PATH.unlink(missing_ok=True)
        load_gif_bytes.clear()
        st.rerun()
