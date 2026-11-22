
import streamlit as st

# Page configuration
st.set_page_config(
    page_title="🌱 English Teacher Certification Exam",
    page_icon="📘",
    layout="wide"
)

# Main page
st.title("🌱 English Teacher Certification Exam")
st.subheader("Past Exam Questions & Interactive Practice")

st.markdown("""
Welcome to the **English Teacher Certification Exam Practice** app!

This app provides an interactive learning environment
for practicing past exam questions from the Korean
Secondary English Teacher Certification Examination.

### 📗 How to Use

1. Select **Exam Practice** from the sidebar.
2. Choose an **exam year** from the dropdown menu.
3. Select a question (e.g., 2026-1, 2026-2, 2026-3).
4. Enter your answers directly into the answer fields.
5. Click **Check Answer** to receive feedback and explanations.

### 📗 Features

- **Year-Based Organization:** Browse questions by exam year.
- **Interactive Practice:** Enter and check your answers.
- **Instant Feedback:** Review correct answers and explanations.
- **Self-Paced Learning:** Practice individual questions
  at your own pace.

---

**Available Exam Year:** 2026

*More exam years and questions will be added over time.*
""")
