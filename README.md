# Study Session — Add-on for the English Teacher Exam Streamlit App

## What it does

This is a **new Streamlit menu/page**, not a replacement for the existing yearly HTML practice pages.

- Start/resume under **name + personal PIN**. An unfinished session resumes across later visits while the database remains available.
- Practice multiple years and questions across multiple sittings.
- Save written answers and automatically check supported objective parts. **Written explanations are marked Review required**, not auto-scored as correct.
- Record elapsed time, question ID, answers, and feedback in a local SQLite database.
- Pause/sign out without finishing, or finish whenever ready.
- Download a **PDF report**, either before or after finishing.

## Install into your existing GitHub repo

Copy these files:

```
REPO_ROOT/
  app.py                          # existing, unchanged
  requirements.txt                # existing, append reportlab>=4.0
  exam_manifest.json              # NEW
  pages/
    Exam_Practice.py              # existing, unchanged
    Exam_Session.py               # NEW
  years/
    2026/index.html + images/     # existing, unchanged
    ...
```

Use the **two files** `pages/Exam_Session.py` and `exam_manifest.json` from this add-on ZIP. Keep the existing `years` directory in your GitHub repo, since this ZIP does **not** duplicate the exam images. Add `reportlab>=4.0` to the existing `requirements.txt` (do not replace existing dependencies). `st.set_page_config()` is called in the new page, but avoid duplicate calls in the same page if your application sets global configuration in a shared entrypoint.

**Question images:** all paths are relative to your existing `years/YYYY/images` folders.

**Adding another year:** the static manifest must be regenerated. Download `scripts/build_manifest.js` into `REPO_ROOT/scripts/` and run `node scripts/build_manifest.js` locally, commit the regenerated `exam_manifest.json`. Node is only required during regeneration, not on Streamlit Cloud. The generator supports the `QUESTIONS` structure used by existing year pages; after new questions are added, **review the generated grading cases** for correctness before publishing.

## Persistence and security — important

This version uses local SQLite (`exam_sessions.sqlite3`). It persists through ordinary app reruns, browser logout, and later visits **as long as the same server files persist**. Streamlit Community Cloud files are **not guaranteed to persist** across app restarts or redeployment, and multiple replicas do not share SQLite; therefore this is a demo/initial rollout, **not durable production storage**. For students returning across days reliably, migrate the database to hosted persistent storage (Supabase/Postgres). Ask for that migration before production launch.

The personal PIN is salted/hashed but **this is not a complete production authentication system** (no password recovery, email verification, access controls, or rate limits). Use pseudonyms or student IDs that are not sensitive, and avoid sending official assessments through this demo.

Timing measures elapsed time between interactive checkpoints while logged in (includes inactivity). Use Pause / Sign out to exclude breaks. If the tab is closed without clicking Save, Check, or Pause, the last interval may be lost. Questions saved as drafts remain available even if not yet graded.

**Important:** The `exam_manifest.json` file contains accepted objective-answer variants for grading, so it must be treated as a server-side resource. If your GitHub repository is public, users may inspect grading keys; move the key data to a private backend for high-stakes testing. Original HTML pages also contain model answers and a client-side password and should not be considered secure.
