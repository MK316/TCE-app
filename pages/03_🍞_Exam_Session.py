"""Exam Practice Session: persistent Supabase study log and downloadable PDF.
Requires: pip install streamlit reportlab supabase
Supabase Secrets: SUPABASE_URL, SUPABASE_SECRET_KEY (server side only).
"""
import hashlib
import hmac
import io
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import streamlit as st
from supabase import create_client
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak, Flowable

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "exam_manifest.json"

st.set_page_config(page_title="Study Session Report", page_icon="📋", layout="wide")
st.title("Study Session & PDF Report")
st.caption("이름과 개인 비밀번호로 시작한 뒤 연도별 문항을 나누어 풀고, 언제든 세션을 종료하여 PDF 결과표를 받을 수 있습니다.")

if not MANIFEST.exists():
    st.error("exam_manifest.json 파일이 없습니다. 프로젝트 최상위 폴더에 추가하세요.")
    st.stop()

if not all(k in st.secrets for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY")):
    st.error("Supabase 설정이 없습니다. Streamlit Secrets에 SUPABASE_URL과 SUPABASE_SECRET_KEY를 등록하세요.")
    st.stop()

QUESTIONS = {q["label"]: q for q in json.loads(MANIFEST.read_text(encoding="utf-8"))}
VALID_IDS = {q_id for q_id, q in QUESTIONS.items() if not q.get("incomplete")}


@st.cache_resource
def get_supabase():
    """Server-only client. Never expose the secret key to HTML or browser code."""
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )


def utcstamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hashed(pin, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), bytes.fromhex(salt), 210000
    ).hex()


def single(rows):
    return rows[0] if rows else None


def signin(name, pin, mode):
    """Authenticate, then either create a fresh session or resume an existing one.

    'new': preserve older rows, close any currently active session, create a
           new empty session. This never copies earlier answers.
    'continue': resume the most recent session, reopening it if finished.
                All previously submitted answers remain associated with it.
    """
    db = get_supabase()
    user = single(
        db.table("exam_users").select("name,salt,pin_hash")
        .eq("name", name).limit(1).execute().data
    )
    if user is None:
        if mode == "continue":
            return None, "기존 계정을 찾을 수 없습니다. '새로 시작하기'를 선택해 주세요."
        salt = os.urandom(16).hex()
        try:
            db.table("exam_users").insert({
                "name": name, "salt": salt, "pin_hash": hashed(pin, salt)
            }).execute()
        except Exception:
            user = single(
                db.table("exam_users").select("name,salt,pin_hash")
                .eq("name", name).limit(1).execute().data
            )
            if user is None:
                raise
    if user is not None and not hmac.compare_digest(
        hashed(pin, user["salt"]), user["pin_hash"]
    ):
        return None, "이름 또는 비밀번호가 일치하지 않습니다."

    existing = (
        db.table("exam_sessions").select("id,status,created_at")
        .eq("name", name).order("created_at", desc=True)
        .limit(100).execute().data or []
    )
    active = next((x for x in existing if x["status"] == "active"), None)

    if mode == "continue":
        if active:
            return active["id"], None
        if existing:
            # Continue the most recent finished session without deleting its
            # answers or time totals. There is no active session here.
            previous = existing[0]
            (db.table("exam_sessions")
             .update({"status": "active", "finished_at": None})
             .eq("id", previous["id"])
             .eq("status", "finished").execute())
            return previous["id"], None
        return None, "이어갈 기록이 없습니다. '새로 시작하기'를 선택해 주세요."

    if mode != "new":
        return None, "올바른 학습 시작 방식을 선택하세요."

    # Existing active session is closed, not overwritten/deleted, to ensure
    # that 'new' always begins with a new, blank checklist. Keep prior PDFs.
