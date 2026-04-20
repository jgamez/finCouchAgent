"""
Project 1 — Vanilla Teacher Agent Web App
FastAPI application serving the lesson experience.
"""

import asyncio
import json
import logging
import sys
import uuid
from collections import defaultdict
from typing import Optional


def _lesson_events_logger() -> logging.Logger:
    """Always log to stderr so lines show under uvicorn, debugpy, and IDE run configs."""
    log = logging.getLogger("fincoach.lesson_events")
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from agent.anthropic_env import (
    anthropic_base_url,
    claude_api_key,
    claude_messages_url,
    default_request_headers,
    load_dotenv_from_project,
)
from agent.lesson_flows.registry import is_valid_flow_id, list_lesson_flows
from agent.teacher_agent import TeacherAgent
from agent.topic_financial import is_financial_education_topic

load_dotenv_from_project()

app = FastAPI(title="FinCoach — Teacher Agent (Vanilla)", version="1.0.0")
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# In-memory session store (swap for Redis in production)
sessions: dict[str, dict] = {}

# One queue per connected SSE client; `_lesson_sse_broadcast` notifies all for a session.
_lesson_sse_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)


def _lesson_sse_broadcast(session_id: str, payload: dict) -> None:
    """Wake lesson page EventSource clients (same asyncio event loop as request handlers)."""
    for q in list(_lesson_sse_queues.get(session_id, [])):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                while True:
                    q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass


# Load Claude API key from environment variables
CLAUDE_API_KEY = claude_api_key()
CLAUDE_API_URL = claude_messages_url()
HEADERS = default_request_headers(CLAUDE_API_KEY or "")

if not CLAUDE_API_KEY:
    raise RuntimeError(
        "Set CLAUDE_API_KEY in project-1-vanilla/.env (Anthropic console API key)."
    )

# AsyncAnthropic sends x-api-key from api_key=; other HEADERS fields go on each request.
teacher = TeacherAgent(
    api_key=CLAUDE_API_KEY,
    base_url=anthropic_base_url(CLAUDE_API_URL),
    default_headers={
        k: v for k, v in HEADERS.items() if k.lower() != "x-api-key" and v
    },
)


# ─── Request/Response Models ──────────────────────────────────────────────────

class StudentProfile(BaseModel):
    name: str
    age: int
    audience_level: str   # middle_school | high_school | college
    proficiency: str      # beginner | intermediate | advanced
    topic: str
    lesson_flow_id: str = "default"

    @field_validator("topic")
    @classmethod
    def must_be_financial_education_topic(cls, v: str) -> str:
        t = (v or "").strip()
        if not t:
            raise ValueError("Please select or enter a financial education topic.")
        if not is_financial_education_topic(t):
            raise ValueError("Please choose only financial education topics.")
        return t

    @field_validator("lesson_flow_id")
    @classmethod
    def validate_lesson_flow_id(cls, v: str) -> str:
        if not is_valid_flow_id(v):
            raise ValueError(f"Unknown lesson_flow_id: {v!r}")
        return v


class AssessmentSubmission(BaseModel):
    session_id: str
    answers: list[dict]


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/lesson/{session_id}", response_class=HTMLResponse)
async def lesson_page(request: Request, session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return templates.TemplateResponse(
        request,
        "lesson.html",
        {"session_id": session_id, "profile": session["profile"]},
    )


# ─── Reference data (used by some UIs / extensions probing /api/*) ────────────


@app.get("/api/grade-levels")
async def api_grade_levels():
    """Education band options (matches `audience_level` on StudentProfile)."""
    return [
        {"value": "middle_school", "label": "Middle School"},
        {"value": "high_school", "label": "High School"},
        {"value": "college", "label": "College"},
    ]


@app.get("/api/difficulty-levels")
async def api_difficulty_levels():
    """Proficiency options (matches `proficiency` on StudentProfile)."""
    return [
        {"value": "beginner", "label": "Beginner"},
        {"value": "intermediate", "label": "Intermediate"},
        {"value": "advanced", "label": "Advanced"},
    ]


@app.get("/api/lesson-flows")
async def api_lesson_flows():
    """Lesson format options for the home-page dropdown."""
    return [
        {"id": m.id, "label": m.label, "description": m.description}
        for m in list_lesson_flows()
    ]


@app.get("/api/homework-types")
async def api_homework_types():
    """Topic-style choices aligned with the home-page topic list."""
    return [
        {"value": "budgeting", "label": "Budgeting & Money Management"},
        {"value": "saving", "label": "Saving & Emergency Funds"},
        {"value": "investing", "label": "Investing & the Stock Market"},
        {"value": "credit", "label": "Credit Scores & Borrowing"},
        {"value": "compound interest", "label": "Compound Interest"},
        {"value": "taxes", "label": "Taxes & Filing"},
        {"value": "insurance", "label": "Insurance Basics"},
        {"value": "student loans", "label": "Student Loans & Financial Aid"},
        {"value": "entrepreneurship", "label": "Entrepreneurship & Side Hustles"},
        {"value": "cryptocurrency", "label": "Cryptocurrency & Digital Assets"},
    ]


@app.post("/api/start-lesson")
async def start_lesson(profile: StudentProfile):
    """
    Kick off lesson generation. Returns session_id immediately.
    The lesson page uses GET /api/lesson/{session_id}/events (SSE) instead of polling.
    """
    session_id = str(uuid.uuid4())
    _log = _lesson_events_logger()
    _bar = "=" * 72
    _log.info(_bar)
    _log.info("[FinCoach] lesson_generation_started")
    _log.info(
        f"  user: {profile.name!r}  |  topic: {profile.topic!r}  |  flow: {profile.lesson_flow_id!r}"
    )
    _log.info(
        f"  level: {profile.audience_level!r}  |  proficiency: {profile.proficiency!r}  |  age: {profile.age}  |  session: {session_id}"
    )
    _log.info(_bar)
    sessions[session_id] = {
        "profile": profile.model_dump(),
        "lesson_flow_id": profile.lesson_flow_id,
        "status": "generating",
        "lesson": None,
        "error": None,
        "generation_log": [],
        "available_steps": 0,
        "total_steps": 0,
    }

    # Fire off lesson generation in background
    asyncio.create_task(_generate_lesson_task(session_id, profile))

    return {"session_id": session_id, "status": "generating"}


@app.get("/api/lesson-status/{session_id}")
async def lesson_status(session_id: str):
    """Poll for lesson generation status."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    log = session.get("generation_log") or []
    phase = log[-1]["message"] if log else "Generating lesson…"
    st = session["status"]
    lesson_payload = session.get("lesson")
    return {
        "status": st,
        "lesson": lesson_payload if st in ("partial", "ready") else None,
        "available_steps": session.get("available_steps", 0),
        "total_steps": session.get("total_steps", 0),
        "error": session.get("error"),
        "generation_log": log,
        "phase": phase,
    }


@app.get("/api/lesson/{session_id}")
async def get_lesson(session_id: str):
    """Return lesson JSON once an outline exists (shell with pending steps) or steps are ready."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] == "error":
        raise HTTPException(status_code=404, detail=session.get("error") or "Generation failed")
    lesson = session.get("lesson")
    tot = session.get("total_steps", 0)
    if lesson and tot >= 1:
        return lesson
    raise HTTPException(status_code=202, detail="Lesson still generating")


def _sse_pack(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.get("/api/lesson/{session_id}/events")
async def lesson_events_sse(session_id: str):
    """
    Server-Sent Events: notify the browser when generation advances so it can
    GET /api/lesson/{session_id} once per update (no interval polling).
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_gen():
        q: asyncio.Queue = asyncio.Queue(maxsize=32)
        _lesson_sse_queues[session_id].append(q)
        try:
            yield _sse_pack({"type": "hello"})
            while session_id in sessions:
                sess = sessions[session_id]
                if sess.get("status") == "error":
                    err = sess.get("error") or "Generation failed"
                    yield _sse_pack({"type": "error", "message": err})
                    return
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25.0)
                except asyncio.TimeoutError:
                    if session_id not in sessions:
                        yield _sse_pack({"type": "gone"})
                        return
                    sess = sessions[session_id]
                    if sess.get("status") == "error":
                        err = sess.get("error") or "Generation failed"
                        yield _sse_pack({"type": "error", "message": err})
                        return
                    yield _sse_pack({"type": "heartbeat"})
                    continue
                yield _sse_pack(msg)
                if msg.get("type") == "error":
                    return
            yield _sse_pack({"type": "gone"})
        finally:
            lst = _lesson_sse_queues.get(session_id)
            if lst and q in lst:
                lst.remove(q)
            if not _lesson_sse_queues.get(session_id):
                _lesson_sse_queues.pop(session_id, None)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/submit-assessment")
async def submit_assessment(submission: AssessmentSubmission):
    """Grade student assessment and return feedback."""
    session = sessions.get(submission.session_id)
    if not session or not session.get("lesson"):
        raise HTTPException(status_code=404, detail="Session or lesson not found")
    if session["status"] != "ready":
        raise HTTPException(
            status_code=400,
            detail="Lesson is still being generated. Finish all steps first.",
        )
    av = session.get("available_steps", 0)
    tot = session.get("total_steps", 0)
    if tot > 0 and av < tot:
        raise HTTPException(
            status_code=400,
            detail="Lesson is still being generated. Wait for all steps to finish.",
        )

    profile = session["profile"]
    feedback = await teacher.grade_assessment(
        lesson=session["lesson"],
        student_answers=submission.answers,
        audience_level=profile["audience_level"],
        proficiency=profile["proficiency"],
    )

    sessions[submission.session_id]["assessment_result"] = feedback
    return feedback


@app.get("/api/assessment-result/{session_id}")
async def get_assessment_result(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get("assessment_result", {})


# ─── Background Task ──────────────────────────────────────────────────────────

async def _generate_lesson_task(session_id: str, profile: StudentProfile):
    """Background task: generate lesson and update session state."""
    log = sessions[session_id].setdefault("generation_log", [])
    log.append(
        {
            "kind": "step",
            "message": "Teacher agent started — loading MCP tools and lesson prompt…",
        }
    )
    async def on_partial(lesson: dict, available: int, total: int) -> None:
        sessions[session_id]["lesson"] = lesson
        sessions[session_id]["available_steps"] = available
        sessions[session_id]["total_steps"] = total
        steps = lesson.get("steps") if isinstance(lesson, dict) else None
        has_outline = isinstance(steps, list) and len(steps) > 0
        if total > 0 and available >= total:
            sessions[session_id]["status"] = "ready"
        elif available >= 1:
            sessions[session_id]["status"] = "partial"
        elif total > 0 and has_outline:
            # Outline shell only (0 steps expanded yet) — still let the client open the lesson UI
            sessions[session_id]["status"] = "partial"
        else:
            sessions[session_id]["status"] = "generating"
        _lesson_sse_broadcast(session_id, {"type": "update"})

    try:
        lesson = await teacher.generate_lesson(
            topic=profile.topic,
            audience_level=profile.audience_level,
            proficiency=profile.proficiency,
            student_name=profile.name,
            age=profile.age,
            progress_events=log,
            on_partial=on_partial,
            lesson_flow_id=profile.lesson_flow_id,
        )
        sessions[session_id]["lesson"] = lesson
        sessions[session_id]["status"] = "ready"
        steps = lesson.get("steps") or []
        sessions[session_id]["available_steps"] = len(steps)
        sessions[session_id]["total_steps"] = len(steps)
        _lesson_sse_broadcast(session_id, {"type": "update"})
    except Exception as e:
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"] = str(e)
        log.append({"kind": "error", "message": str(e)})
        _lesson_sse_broadcast(session_id, {"type": "error", "message": str(e)})


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "mode": "vanilla"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
