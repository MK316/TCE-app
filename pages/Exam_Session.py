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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

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
            con.execute("UPDATE attempts SET seconds=seconds+? WHERE session_id=? AND question_id=?",(round(add_seconds,2),sid,qid))
        con.commit()


def norm(value):
    s=str(value or "").strip().casefold().replace("−","-").replace("–","-")
    s=re.sub(r"[\[\]{}()/\s]", "",s)
    s=s.translate(str.maketrans("①②③④⑤","12345"))
    return s


def normalized_choice(value):
    text=str(value or "").casefold().strip()
    # Treat comma-separated choices as a set only if the entire string is made of option labels.
    if re.fullmatch(r"[a-d](?:\s*[,;/& ]\s*[a-d])*",text):
        return "".join(sorted(set(re.findall(r"[a-d]",text))))
    return norm(value)


def grade(q, values):
    results=[]
    for i, info in enumerate(q.get("grade_labels", [])):
        if info.get("review"):
            written=any(str(v).strip() for v in values.values())
            results.append({"label":info["label"],"result":"Review required" if written else "Not answered"})
            continue
        rule=next((c for c in q.get("grade_cases",[]) if c["index"]==i),None)
        if not rule:
            results.append({"label":info["label"],"result":"Review required"})
            continue
        correct=False
        for accepted in rule.get("accepted",[]):
            if all(normalized_choice(values.get(fid,""))==normalized_choice(expected) for fid,expected in accepted.items()):
                correct=True;break
        submitted=any(str(v).strip() for v in values.values())
        results.append({"label":info["label"],"result":"Correct" if correct else ("Incorrect" if submitted else "Not answered")})
    return results


def tick(sid):
    """Count wall-clock time only while this Streamlit browser tab is active.
    Elapsed time includes idle time until an interaction; pause/finish explicitly.
    """
    key=st.session_state.get("clock_key")
    then=st.session_state.get("clock_at")
    now=time.monotonic()
    if key and then and st.session_state.get("session_id")==sid:
        persist(sid,key,add_seconds=max(0,min(now-then,86400)))
    st.session_state["clock_at"]=now


def set_question(qid):
    st.session_state["clock_key"]=qid
    st.session_state["clock_at"]=time.monotonic()


def report_pdf(sid, name):
    with connection() as con:
        session=con.execute("SELECT * FROM sessions WHERE id=?",(sid,)).fetchone()
    records=attempt_rows(sid)
    buffer=io.BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    font="HYGothic-Medium"
    doc=SimpleDocTemplate(buffer,pagesize=A4,leftMargin=19*mm,rightMargin=19*mm,topMargin=18*mm,bottomMargin=18*mm)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="KTitle",fontName=font,fontSize=17,leading=24,textColor=colors.HexColor("#16365C"),spaceAfter=12))
    styles.add(ParagraphStyle(name="KBody",fontName=font,fontSize=9.5,leading=15,spaceAfter=5,wordWrap="CJK"))
    styles.add(ParagraphStyle(name="KSmall",fontName=font,fontSize=8,leading=12,wordWrap="CJK"))
    styles.add(ParagraphStyle(name="KHeading",fontName=font,fontSize=11,leading=17,spaceBefore=14,spaceAfter=7,textColor=colors.HexColor("#173154")))
    P=lambda text,sty="KBody":Paragraph(escape(str(text)).replace("\n","<br/>"),styles[sty])
    completed=[(qid,r) for qid,r in records.items() if r["checked_at"] or json.loads(r["answers"])]
    seconds=sum(r["seconds"] for r in records.values())
    total_correct=sum(item.get("result")=="Correct" for _,r in completed for item in json.loads(r["feedback"]))
    total_scored=sum(item.get("result") in ("Correct","Incorrect") for _,r in completed for item in json.loads(r["feedback"]))
    story=[P("English Teacher Exam | Study Report","KTitle"),
           P("Learner: "+name),P("Session ID: "+sid),P("Started: "+session["created_at"]),
           P("Report generated: "+utcstamp()),P("Status: "+session["status"]),
           P("Questions attempted: "+str(len(completed))+"  |  Recorded duration: "+f"{seconds/60:.1f} minutes"),
           P(f"Auto-checked items: {total_correct}/{total_scored}  (written responses excluded)"),
           P("Timing is elapsed session time between interactions, not a precise measure of focused attention.","KSmall")]
    for qid,r in sorted(completed,reverse=True):
        q=QUESTIONS.get(qid,{"fields":[],"year":qid[:4]})
        answers=json.loads(r["answers"])
        feedback=json.loads(r["feedback"])
        block=[P(f"{qid}  |  Exam year {q['year']}  |  {r['seconds']/60:.1f} min","KHeading")]
        for f in q.get("fields",[]):
            block.append(P(str(f["label"])+": "+(str(answers.get(f["id"],"")) or "(blank)")))
        block.append(P("Feedback: "+("; ".join(x["label"]+" = "+x["result"] for x in feedback) if feedback else "Not checked"),"KSmall"))
        if r["checked_at"]:block.append(P("Checked at: "+r["checked_at"],"KSmall"))
        story.append(KeepTogether(block))
    if not completed: story.append(P("No answers have been submitted in this session."))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# Login-like session start. Name + PIN is only for this demo database, not production auth.
if not st.session_state.get("session_id"):
    st.subheader("Start or resume a session")
    with st.form("session_login"):
        name=st.text_input("User name",max_chars=70)
        pin=st.text_input("Personal PIN (at least 4 characters)",type="password")
        submitted=st.form_submit_button("Start / Resume",type="primary")
    if submitted:
        if len(name.strip())<2 or len(pin)<4:
            st.error("이름은 2자 이상, 개인 비밀번호는 4자 이상 입력하세요.")
        else:
            sid, error=signin(name.strip(), pin)
            if error:st.error(error)
            else:
                st.session_state["session_id"]=sid
                st.session_state["user_name"]=name.strip()
                st.session_state["clock_key"]=None
                st.rerun()
    st.info("기존 기록은 같은 이름과 개인 비밀번호로 다시 접속하면 이어서 진행합니다. 로그인은 정식 인증 서비스가 아닌 간단한 학습용 인증입니다.")
    st.stop()

sid=st.session_state["session_id"]
name=st.session_state["user_name"]
with connection() as con:
    db_session=con.execute("SELECT * FROM sessions WHERE id=?",(sid,)).fetchone()
if not db_session:
    st.session_state.pop("session_id",None);st.rerun()

if db_session["status"]=="active":
    tick(sid)

st.markdown(f"**Learner:** {name}  ·  **Started:** {db_session['created_at']}")
rows=attempt_rows(sid)
answered=sum(bool(r["checked_at"]) for r in rows.values())
elapsed=sum(r["seconds"] for r in rows.values())
col1,col2,col3=st.columns(3)
col1.metric("Checked questions",answered)
col2.metric("Recorded time",f"{elapsed/60:.1f} min")
col3.metric("Years available",len({q["year"] for q in QUESTIONS.values()}))

if db_session["status"]=="finished":
    st.success("This session is finished. The report is available below.")
    st.download_button("Download PDF report",report_pdf(sid,name),file_name=f"exam_report_{sid[:8]}.pdf",mime="application/pdf",type="primary")
    if st.button("Start a new session"):
        st.session_state.pop("session_id",None)
        st.session_state["clock_key"]=None
        with connection() as con:
            new_sid=str(uuid.uuid4())
            con.execute("INSERT INTO sessions (id,name,created_at,status) VALUES (?,?,?,'active')",(new_sid,name,utcstamp()))
            con.commit()
        st.session_state["session_id"]=new_sid
        st.rerun()
    st.stop()

st.divider()
years=sorted({q["year"] for q in QUESTIONS.values()}, reverse=True)
year=st.selectbox("Select exam year",years,key="session_year")
year_questions=[q for q in QUESTIONS.values() if q["year"]==year]
labels=[q["label"] for q in year_questions]
qid=st.radio("Select question",labels,horizontal=True,key="session_question") if labels else None
if not qid: st.stop()
q=QUESTIONS[qid]
if st.session_state.get("clock_key")!=qid: set_question(qid)

st.subheader(f"Question {qid}")
st.caption(f"{q.get('original','')} · {q.get('points','')}")
# Display every original page image without revealing the model answers.
for image_path in q.get("images",[]):
    f=ROOT/"years"/year/image_path
    if f.exists():st.image(str(f),use_container_width=False)
    else:st.error(f"Missing question image: {year}/{image_path}")
if q.get("extraInstruction"): st.write(q["extraInstruction"])
if q.get("incomplete"):
    st.warning("이 문항은 원문 일부가 누락되어 아직 채점할 수 없습니다.")
else:
    st.markdown("**Your answer**")
    old=json.loads(rows.get(qid,{}).get("answers","{}"))
    # A dedicated key per question preserves partially edited fields during Streamlit reruns.
    with st.form("answer_form_"+qid):
        values={}
        for f in q.get("fields",[]):
            wk="answer_"+qid+"_"+f["id"]
            if wk not in st.session_state:st.session_state[wk]=old.get(f["id"],"")
            if f["type"]=="textarea":
                values[f["id"]]=st.text_area(f["label"],key=wk,height=100)
            elif f["type"]=="choice":
                st.session_state[wk]=str(st.session_state[wk]) if st.session_state[wk] is not None else ""
                options=["","1","2","3","4","5"]
                if st.session_state[wk] not in options:st.session_state[wk]=""
                values[f["id"]]=st.selectbox(f["label"],options,key=wk,format_func=lambda v:{"":"Choose one","1":"①","2":"②","3":"③","4":"④","5":"⑤"}[v])
            else:values[f["id"]]=st.text_input(f["label"],key=wk)
        save=st.form_submit_button("Save answer",type="secondary")
        check=st.form_submit_button("Check & record",type="primary")
    if save or check:
        # Record the interval since the form was displayed.
        tick(sid)
        if check:
            results=grade(q,values)
            persist(sid,qid,answers=values,feedback=results,checked=True)
            st.success("Answer and grading result recorded.")
        else:
            persist(sid,qid,answers=values)
            st.success("Draft saved.")
        rows=attempt_rows(sid)
    feedback=json.loads(rows.get(qid,{}).get("feedback","[]"))
    if feedback:
        st.markdown("**Recorded feedback**")
        for item in feedback:st.write(f"{item['label']}: **{item['result']}**")
    st.caption("Written explanations are recorded as ‘Review required’; they are not automatically marked correct. For model answers, use the existing password-protected yearly practice page.")

st.divider()
left, mid, right=st.columns(3)
with left:
    if st.button("Pause / Sign out"):
        tick(sid)
        st.session_state["clock_key"]=None
        st.session_state.pop("session_id",None)
        st.session_state.pop("user_name",None)
        st.rerun()
with mid:
    st.download_button("Download current PDF",report_pdf(sid,name),file_name=f"exam_progress_{sid[:8]}.pdf",mime="application/pdf")
with right:
    if st.button("Finish session",type="primary"):
        tick(sid)
        with connection() as con:
            con.execute("UPDATE sessions SET status='finished', finished_at=? WHERE id=?",(utcstamp(),sid))
            con.commit()
        st.session_state["clock_key"]=None
        st.rerun()

st.caption("Important: The sample SQLite file stored on Streamlit Community Cloud can be lost on app restart/redeployment. For reliable long-term records, connect a managed database such as Supabase. Save interim PDFs as backups. Use Pause / Sign out to stop the timer.")
