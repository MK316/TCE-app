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


def signin(name, pin):
    """Register if new, otherwise verify PIN and resume one active session."""
    db = get_supabase()
    user = single(
        db.table("exam_users").select("name,salt,pin_hash").eq("name", name)
        .limit(1).execute().data
    )
    if user is None:
        salt = os.urandom(16).hex()
        try:
            db.table("exam_users").insert({
                "name": name, "salt": salt, "pin_hash": hashed(pin, salt)
            }).execute()
        except Exception:
            # If two browsers register the same name simultaneously, verify
            # the already-created account rather than overwriting its PIN.
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

    session = single(
        db.table("exam_sessions").select("*").eq("name", name)
        .eq("status", "active").order("created_at", desc=True)
        .limit(1).execute().data
    )
    if session:
        return session["id"], None

    sid = str(uuid.uuid4())
    try:
        db.table("exam_sessions").insert({
            "id": sid, "name": name, "status": "active"
        }).execute()
    except Exception:
        # Unique active-session index handles simultaneous logins safely.
        session = single(
            db.table("exam_sessions").select("id").eq("name", name)
            .eq("status", "active").limit(1).execute().data
        )
        if not session:
            raise
        sid = session["id"]
    return sid, None


def session_row(sid):
    return single(
        get_supabase().table("exam_sessions").select("*")
        .eq("id", sid).limit(1).execute().data
    )


def attempt_rows(sid):
    response = (
        get_supabase().table("exam_attempts").select("*")
        .eq("session_id", sid).order("question_id").execute()
    )
    # Keep the existing report/UI format compatible with JSON strings,
    # while PostgreSQL stores answers and feedback natively as JSONB.
    rows = {}
    for record in response.data:
        record = dict(record)
        for key, default in (("answers", {}), ("feedback", [])):
            if isinstance(record.get(key), (dict, list)):
                record[key] = json.dumps(record[key], ensure_ascii=False)
            elif record.get(key) is None:
                record[key] = json.dumps(default)
        rows[record["question_id"]] = record
    return rows


def persist(sid, qid, answers=None, feedback=None, add_seconds=0, checked=False):
    db = get_supabase()
    # Insert once without clobbering a row written by another open tab.
    db.table("exam_attempts").upsert(
        {"session_id": sid, "question_id": qid,
         "answers": {}, "feedback": [], "seconds": 0},
        on_conflict="session_id,question_id", ignore_duplicates=True
    ).execute()

    update = {}
    if answers is not None:
        update["answers"] = answers
    if feedback is not None:
        update["feedback"] = feedback
        if checked:
            update["checked_at"] = utcstamp()
    if update:
        (db.table("exam_attempts").update(update)
         .eq("session_id", sid).eq("question_id", qid).execute())
    if add_seconds > 0:
        # Database-side atomic increment protects against concurrent logins.
        db.rpc("exam_add_attempt_seconds", {
            "p_session_id": sid,
            "p_question_id": qid,
            "p_seconds": round(float(add_seconds), 2),
        }).execute()


def finish_session(sid):
    (get_supabase().table("exam_sessions")
     .update({"status": "finished", "finished_at": utcstamp()})
     .eq("id", sid).eq("status", "active").execute())


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
            relevant_id = q.get("fields", [])[i]["id"] if i < len(q.get("fields", [])) else None
            written = (str(values.get(relevant_id, "")).strip() if relevant_id else
                       any(str(v).strip() for v in values.values()))
            results.append({"label": info["label"],
                            "result": "Review required" if written else "Not answered"})
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
    """Build a color-coded, multipage learner report (without model-answer leakage)."""
    session = session_row(sid)
    if not session:
        raise ValueError("Study session not found")
    records = attempt_rows(sid)
    buffer = io.BytesIO()
    # Prefer a locally installed Korean/Latin TTF for more natural letter spacing.
    # Fall back to ReportLab's built-in Korean CID font for portability.
    from reportlab.pdfbase.ttfonts import TTFont
    candidate_fonts = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
        "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
    ]
    font = "HYGothic-Medium"
    for candidate in candidate_fonts:
        if Path(candidate).is_file():
            try:
                pdfmetrics.registerFont(TTFont("StudyReportKorean", candidate))
                font = "StudyReportKorean"
                break
            except Exception:
                pass
    if font == "HYGothic-Medium":
        pdfmetrics.registerFont(UnicodeCIDFont(font))

    NAVY = colors.HexColor("#173154")
    BLUE = colors.HexColor("#2563EB")
    GREEN = colors.HexColor("#087951")
    RED = colors.HexColor("#B42332")
    ORANGE = colors.HexColor("#B65A16")
    DARK = colors.HexColor("#233047")
    MUTED = colors.HexColor("#5B6B80")
    LINE = colors.HexColor("#DCE4EF")
    LIGHT = colors.HexColor("#F4F7FB")
    WHITE = colors.white
    status_colors = {
        "Correct": GREEN,
        "Review required": BLUE,
        "Not answered": RED,
        "Incorrect": ORANGE,
        "Not checked": MUTED,
    }
    status_labels = {
        "Correct": "Correct",
        "Review required": "Review required",
        "Not answered": "Not answered",
        "Incorrect": "Incorrect",
        "Not checked": "Not checked",
    }

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=20*mm, bottomMargin=19*mm,
        title="English Teacher Exam - Study Report",
        author="English Teacher Exam Practice"
    )
    content_width = A4[0] - 36*mm
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="RTitle", fontName=font, fontSize=20, leading=27,
                              textColor=NAVY, spaceAfter=7))
    styles.add(ParagraphStyle(name="RSubtitle", fontName=font, fontSize=9, leading=14,
                              textColor=MUTED, spaceAfter=15))
    styles.add(ParagraphStyle(name="RSection", fontName=font, fontSize=12, leading=18,
                              textColor=NAVY, spaceBefore=13, spaceAfter=8))
    styles.add(ParagraphStyle(name="RBody", fontName=font, fontSize=9.1, leading=14.4,
                              textColor=DARK, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="RSmall", fontName=font, fontSize=8.1, leading=12.3,
                              textColor=MUTED, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="RStrong", fontName=font, fontSize=9, leading=14,
                              textColor=NAVY, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="RChecklist", fontName=font, fontSize=8.1, leading=12,
                              textColor=DARK, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="RStatus", fontName=font, fontSize=8.2, leading=12.5,
                              textColor=NAVY, wordWrap="CJK"))

    def par(value, style="RBody", keep_newlines=False):
        plain = escape(str(value))
        if keep_newlines:
            plain = plain.replace("\n", "<br/>")
        return Paragraph(plain, styles[style])

    def status_par(status):
        color = status_colors.get(status, MUTED).hexval()
        return Paragraph(f'<font color="{color}">{escape(status_labels.get(status, status))}</font>', styles["RStatus"])

    def display_time(seconds):
        seconds = max(0, int(round(float(seconds or 0))))
        hours, rem = divmod(seconds, 3600)
        mins, secs = divmod(rem, 60)
        return f"{hours}h {mins}m {secs}s" if hours else f"{mins}m {secs}s"

    def read_answers(record):
        try:
            return json.loads(record["answers"] or "{}")
        except (TypeError, ValueError):
            return {}

    def read_feedback(record):
        try:
            return json.loads(record["feedback"] or "[]")
        except (TypeError, ValueError):
            return []

    def report_status(record):
        answer_values = read_answers(record)
        nonempty = any(str(value).strip() for value in answer_values.values())
        if not nonempty:
            return "Not answered"
        flags = [item.get("result") for item in read_feedback(record)]
        if "Incorrect" in flags:
            return "Incorrect"
        if "Not answered" in flags:
            return "Not answered"
        if "Review required" in flags:
            return "Review required"
        if flags and all(flag == "Correct" for flag in flags):
            return "Correct"
        return "Not checked"

    # Include saved or checked questions, not merely pages visited for timing.
    attempted = [
        (qid, rec) for qid, rec in records.items()
        if rec["checked_at"] or any(str(v).strip() for v in read_answers(rec).values())
    ]
    attempted.sort(key=lambda row: (row[0][:4], row[0]), reverse=True)
    years = sorted({qid.split("-")[0] for qid, _ in attempted}, reverse=True)
    elapsed = sum(float(rec["seconds"] or 0) for rec in records.values())
    statuses = [report_status(rec) for _, rec in attempted]
    counts = {status: statuses.count(status) for status in status_labels}

    class ChecklistItem(Flowable):
        """Render a reliable checkbox/tick as vector paths, independent of font glyphs."""
        def __init__(self, qid, checked):
            Flowable.__init__(self)
            self.qid = qid
            self.checked = checked
            self.width = 90
            self.height = 13

        def draw(self):
            c = self.canv
            x, y, side = 1.0, 2.0, 9.0
            stroke = GREEN if self.checked else MUTED
            c.setStrokeColor(stroke)
            c.setLineWidth(0.85)
            c.roundRect(x, y, side, side, 1.3, fill=0, stroke=1)
            if self.checked:
                c.setLineWidth(1.45)
                p = c.beginPath()
                p.moveTo(x+1.5, y+4.4)
                p.lineTo(x+3.8, y+2.0)
                p.lineTo(x+7.6, y+7.5)
                c.drawPath(p)
            c.setFont(font, 9)
            c.setFillColor(GREEN if self.checked else DARK)
            c.drawString(15, 2.3, self.qid)

    # Page 1: all available exam questions, with a check only for submitted/checked questions.
    # Drafts and page visits are intentionally NOT counted as completed.
    checked_ids = {
        qid for qid, record in records.items()
        if record.get("checked_at") and qid in QUESTIONS
    }
    all_ids = sorted(QUESTIONS, key=lambda label: (int(QUESTIONS[label]["year"]),
                      int(label.split("-")[-1])), reverse=True)
    checked_count = len(checked_ids)
    latest_check = max((str(record["checked_at"]) for record in records.values()
                        if record.get("checked_at")), default="No submissions")

    story = [
        par("ENGLISH TEACHER EXAM", "RSmall"),
        par("Study Session Report", "RTitle"),
        par("Learner & Session Information", "RSection"),
    ]
    learner_data = [
        [par("Learner", "RStrong"), par(name)],
        [par("Session ID", "RStrong"), par(sid)],
        [par("Started", "RStrong"), par(session["created_at"])],
        [par("Last submission", "RStrong"), par(latest_check)],
        [par("Finished", "RStrong"), par(session["finished_at"] or "In progress")],
        [par("Report generated", "RStrong"), par(utcstamp())],
        [par("Session status", "RStrong"), par(session["status"].title())],
        [par("Recorded time", "RStrong"), par(display_time(elapsed))],
    ]
    learner_table = Table(learner_data, colWidths=[42*mm, content_width-42*mm], hAlign="LEFT")
    learner_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,-1),LIGHT),
        ("ROWBACKGROUNDS",(1,0),(1,-1),[WHITE,colors.HexColor("#FAFCFF")]),
        ("BOX",(0,0),(-1,-1),0.7,LINE),
        ("INNERGRID",(0,0),(-1,-1),0.35,LINE),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),9),
        ("RIGHTPADDING",(0,0),(-1,-1),9),
        ("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    story.append(learner_table)
    story.append(par("All Exam Questions", "RSection"))
    story.append(par(f"Checked: {checked_count} / {len(all_ids)} questions.  "
                     "A check mark means the learner submitted an answer for checking.", "RSmall"))
    # Each row displays four question IDs. Colors mark attempted items; unchecked
    # boxes remain neutral. Use text glyphs compatible with registered Korean fonts.
    num_cols = 4
    cell_rows = []
    for offset in range(0, len(all_ids), num_cols):
        group = all_ids[offset:offset + num_cols]
        row = []
        for qid in group:
            row.append(ChecklistItem(qid, qid in checked_ids))
        row.extend([""] * (num_cols-len(row)))
        cell_rows.append(row)
    checklist = Table(cell_rows, colWidths=[content_width / num_cols] * num_cols, hAlign="LEFT")
    checklist.setStyle(TableStyle([
        ("BOX",(0,0),(-1,-1),0.7,LINE),
        ("INNERGRID",(0,0),(-1,-1),0.35,LINE),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[WHITE,LIGHT]),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),10),
        ("RIGHTPADDING",(0,0),(-1,-1),5),
        ("TOPPADDING",(0,0),(-1,-1),7),
        ("BOTTOMPADDING",(0,0),(-1,-1),7),
    ]))
    story.append(checklist)
    story.append(Spacer(1, 10))
    story.append(par("Green check: submitted/checked. Empty box: not checked. "
                     "Saved drafts are not marked complete.", "RSmall"))
    # A hard page break guarantees that detailed answer records start on page 2.
    story.append(PageBreak())
    story.append(par("ENGLISH TEACHER EXAM", "RSmall"))
    story.append(par("Answer & Feedback Details", "RTitle"))
    story.append(par("Answers, grading outcomes and recorded time for this session.", "RSubtitle"))
    story.append(par("Practice Overview", "RSection"))
    overview = Table([
        [par("Questions", "RSmall"), par("Exam years", "RSmall"), par("Correct", "RSmall"), par("Review required", "RSmall")],
        [par(str(len(attempted)), "RStrong"), par(str(len(years)), "RStrong"),
         par(str(counts["Correct"]), "RStrong"), par(str(counts["Review required"]), "RStrong")],
    ], colWidths=[content_width/4]*4)
    overview.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),LIGHT),
        ("BOX",(0,0),(-1,-1),0.7,LINE),
        ("INNERGRID",(0,0),(-1,-1),0.4,LINE),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),12),
        ("TOPPADDING",(0,0),(-1,-1),7),
        ("BOTTOMPADDING",(0,0),(-1,-1),7),
    ]))
    story.append(overview)
    story.append(Spacer(1, 8))
    legend = Table([[par(status,"RSmall") for status in
                    ("Correct", "Review required", "Not answered", "Incorrect")]],
                   colWidths=[content_width/4]*4)
    legend.setStyle(TableStyle([
        ("TEXTCOLOR",(0,0),(0,0),GREEN),
        ("TEXTCOLOR",(1,0),(1,0),BLUE),
        ("TEXTCOLOR",(2,0),(2,0),RED),
        ("TEXTCOLOR",(3,0),(3,0),ORANGE),
        ("LINEBELOW",(0,0),(0,0),2.8,GREEN),
        ("LINEBELOW",(1,0),(1,0),2.8,BLUE),
        ("LINEBELOW",(2,0),(2,0),2.8,RED),
        ("LINEBELOW",(3,0),(3,0),2.8,ORANGE),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("LEFTPADDING",(0,0),(-1,-1),8),
    ]))
    story.append(legend)
    story.append(par("Exam Questions Practiced", "RSection"))

    if attempted:
        summary_data = [[par("Question", "RStrong"), par("Exam year", "RStrong"),
                         par("Time", "RStrong"), par("Result", "RStrong")]]
        for qid, rec in attempted:
            status = report_status(rec)
            summary_data.append([
                par(qid), par(qid.split("-")[0]),
                par(display_time(rec["seconds"])), status_par(status),
            ])
        col_widths = [34*mm, 33*mm, 42*mm, content_width-109*mm]
        summary = Table(summary_data, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
        ts = [
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E9EFF7")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,LIGHT]),
            ("BOX",(0,0),(-1,-1),0.7,LINE),
            ("LINEBELOW",(0,0),(-1,0),0.8,LINE),
            ("LINEBELOW",(0,1),(-1,-2),0.35,LINE),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),9),
            ("TOPPADDING",(0,0),(-1,-1),7),
            ("BOTTOMPADDING",(0,0),(-1,-1),7),
        ]
        for i, (_, rec) in enumerate(attempted, start=1):
            ts.append(("TEXTCOLOR",(3,i),(3,i),status_colors[report_status(rec)]))
        summary.setStyle(TableStyle(ts))
        story.append(summary)
    else:
        story.append(par("No answers have been saved or checked in this session."))

    story.append(par("Question Details", "RSection"))
    for qid, rec in attempted:
        q = QUESTIONS.get(qid, {"fields":[], "year":qid[:4]})
        answers = read_answers(rec)
        feedback = read_feedback(rec)
        status = report_status(rec)
        detail = [
            [par(f"{qid}  |  {display_time(rec['seconds'])}","RStrong"),status_par(status)]
        ]
        for field in q.get("fields",[]):
            answer = str(answers.get(field["id"],"")).strip()
            detail.append([par(field["label"],"RSmall"),
                           par(answer if answer else "(Not answered)","RBody",True)])
        if feedback:
            # Keep grading per field visible, including partially completed responses.
            individual = "; ".join(f"{f.get('label','Item')}: {f.get('result','Not checked')}" for f in feedback)
            detail.append([par("Feedback", "RSmall"),par(individual,"RSmall",True)])
        if rec["checked_at"]:
            detail.append([par("Checked at", "RSmall"),par(rec["checked_at"],"RSmall")])
        detail_table=Table(detail, colWidths=[49*mm,content_width-49*mm],hAlign="LEFT")
        detail_table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EFF4FB")),
            ("LINEBEFORE",(0,0),(0,0),3.2,status_colors[status]),
            ("BOX",(0,0),(-1,-1),0.6,LINE),
            ("LINEBELOW",(0,0),(-1,-2),0.35,LINE),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),10),
            ("RIGHTPADDING",(0,0),(-1,-1),10),
            ("TOPPADDING",(0,0),(-1,-1),7),
            ("BOTTOMPADDING",(0,0),(-1,-1),7),
            ("TEXTCOLOR",(1,0),(1,0),status_colors[status]),
        ]))
        story.append(Spacer(1, 8))
        story.append(detail_table)

    story.append(Spacer(1, 14))
    story.append(par("Note: Written responses require manual review. The time shown is elapsed time between interactions and may include idle time.","RSmall"))
    story.append(par("This report shows submitted answers and feedback, not the password-protected model answers.","RSmall"))

    def footer(canvas, document):
        canvas.saveState()
        width,_ = A4
        canvas.setStrokeColor(LINE)
        canvas.line(18*mm, 15*mm, width-18*mm,15*mm)
        canvas.setFont(font,7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18*mm,10.5*mm,"ENGLISH TEACHER EXAM  |  STUDY SESSION REPORT")
        canvas.drawRightString(width-18*mm,10.5*mm,f"Page {document.page}")
        canvas.restoreState()

    doc.build(story,onFirstPage=footer,onLaterPages=footer)
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
            try:
                sid, error = signin(name.strip(), pin)
                if error:
                    st.error(error)
                else:
                    st.session_state["session_id"] = sid
                    st.session_state["user_name"] = name.strip()
                    st.session_state["clock_key"] = None
                    st.rerun()
            except Exception:
                st.error("로그인/저장 중 오류가 발생했습니다. Supabase 테이블과 연결 설정을 확인하세요.")
    st.info("기존 기록은 같은 이름과 개인 비밀번호로 다시 접속하면 이어서 진행합니다. 로그인은 정식 인증 서비스가 아닌 간단한 학습용 인증입니다.")
    st.stop()

sid=st.session_state["session_id"]
name=st.session_state["user_name"]
db_session = session_row(sid)
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
        # Return to the login form. A new session is created only
        # after the learner enters their name and PIN.
        st.session_state.pop("session_id", None)
        st.session_state.pop("user_name", None)
        st.session_state["clock_key"] = None
        st.session_state["clock_at"] = None
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
        finish_session(sid)
        st.session_state["clock_key"]=None
        st.rerun()

st.caption("Study records are stored in Supabase. Pause / Sign out stops timing; Finish session closes the current study session. Keep PDF reports as personal backups.")
