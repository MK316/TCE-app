"""교사의 꿈 졸라맨 애니메이션 - Streamlit 앱

실행:  streamlit run app.py
(같은 폴더에 make_gif.py 가 있어야 하며, teacher_dream.gif 가 없으면 자동 생성)
"""
import base64
from pathlib import Path

import streamlit as st

from make_gif import generate

HERE = Path(__file__).parent
GIF_PATH = HERE / "teacher_dream.gif"

st.set_page_config(page_title="졸라맨, 선생님이 되다", page_icon="🍎", layout="centered")


@st.cache_data(show_spinner="애니메이션을 그리는 중...")
def load_gif_bytes() -> bytes:
    if not GIF_PATH.exists():
        generate(str(GIF_PATH))
    return GIF_PATH.read_bytes()


st.title("🍎 졸라맨, 선생님이 되다")
st.caption("교사를 꿈꾸는 대학생의 1~4학년 성장 이야기")

gif = load_gif_bytes()

# base64로 넣으면 어느 Streamlit 버전에서도 GIF가 확실히 움직입니다.
b64 = base64.b64encode(gif).decode()
st.markdown(
    f'<img src="data:image/gif;base64,{b64}" '
    f'style="width:100%;border-radius:12px;border:1px solid #ddd;" alt="교사의 꿈 애니메이션">',
    unsafe_allow_html=True,
)

with st.expander("📚 학년별 이야기 보기"):
    st.markdown(
        """
- **1학년** · 사범대학 입학, 교육학 개론부터 차근차근
- **2학년** · 밤늦게까지 전공 공부에 몰두
- **3학년** · 친구들 앞에서 모의수업 연습
- **4학년** · 교육실습과 임용시험, 그리고 합격!
- **졸업 후** · 드디어 교실에 선 선생님 🎉
"""
    )

col1, col2 = st.columns(2)
with col1:
    st.download_button("⬇️ GIF 다운로드", gif, file_name="teacher_dream.gif", mime="image/gif")
with col2:
    if st.button("🔄 GIF 다시 만들기"):
        GIF_PATH.unlink(missing_ok=True)
        load_gif_bytes.clear()
        st.rerun()
