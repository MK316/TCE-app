"""Exam Practice Session: resumable SQLite study log and downloadable PDF.
Install: copy to pages/Exam_Session.py and copy exam_manifest.json to project root.
Requires: pip install reportlab
"""
import hashlib
import hmac
import io
import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime
from html import escape
from pathlib import Path

import streamlit as st
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
DB_PATH = Path(os.environ.get("EXAM_SESSION_DB", str(ROOT / "exam_sessions.sqlite3")))

st.set_page_config(page_title="Study Session Report", page_icon="📋", layout="wide")
st.title("Study Session & PDF Report")
st.caption("이름과 개인 비밀번호로 시작한 뒤 연도별 문항을 나누어 풀고, 언제든 세션을 종료하여 PDF 결과표를 받을 수 있습니다.")

if not MANIFEST.exists():
    st.error("exam_manifest.json 파일이 없습니다. 프로젝트 최상위 폴더에 추가하세요.")
    st.stop()

QUESTIONS = {q["label"]: q for q in json.loads(MANIFEST.read_text(encoding="utf-8"))}
VALID_IDS = {q_id for q_id, q in QUESTIONS.items() if not q.get("incomplete")}


def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY, salt TEXT NOT NULL, pin_hash TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, finished_at TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS attempts (session_id TEXT NOT NULL, question_id TEXT NOT NULL, answers TEXT NOT NULL DEFAULT '{}', feedback TEXT NOT NULL DEFAULT '[]', seconds REAL NOT NULL DEFAULT 0, checked_at TEXT, PRIMARY KEY(session_id, question_id))")
    con.commit()
    return con


def utcstamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def hashed(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt), 210000).hex()


def signin(name, pin):
    with connection() as con:
        user = con.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
        if user:
            if not hmac.compare_digest(hashed(pin, user["salt"]), user["pin_hash"]):
                return None, "이름 또는 비밀번호가 일치하지 않습니다."
        else:
            salt=os.urandom(16).hex()
            con.execute("INSERT INTO users VALUES (?,?,?)", (name, salt, hashed(pin,salt)))
        session=con.execute("SELECT * FROM sessions WHERE name=? AND status='active' ORDER BY created_at DESC LIMIT 1",(name,)).fetchone()
        if not session:
            sid=str(uuid.uuid4())
            con.execute("INSERT INTO sessions (id,name,created_at,status) VALUES (?,?,?,'active')",(sid,name,utcstamp()))
        else:
            sid=session["id"]
        con.commit()
    return sid, None


def attempt_rows(sid):
    with connection() as con:
        rows=con.execute("SELECT * FROM attempts WHERE session_id=? ORDER BY question_id", (sid,)).fetchall()
    return {r["question_id"]: dict(r) for r in rows}


def persist(sid, qid, answers=None, feedback=None, add_seconds=0, checked=False):
    with connection() as con:
        con.execute("INSERT OR IGNORE INTO attempts (session_id,question_id,answers,feedback,seconds) VALUES (?,?,'{}','[]',0)",(sid,qid))
        if answers is not None:
            con.execute("UPDATE attempts SET answers=? WHERE session_id=? AND question_id=?", (json.dumps(answers,ensure_ascii=False),sid,qid))
        if feedback is not None:
            con.execute("UPDATE attempts SET feedback=?,checked_at=? WHERE session_id=? AND question_id=?",(json.dumps(feedback,ensure_ascii=False),utcstamp() if checked else None,sid,qid))
        if add_seconds>0:
