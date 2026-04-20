"""
Project 1 — Vanilla Teacher Agent Web App
FastAPI application serving the lesson experience.
"""

import json
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from agent.anthropic_env import (
    anthropic_base_url,
    claude_api_key,
    claude_messages_url,
    default_request_headers,
    load_dotenv_from_project,
)
from agent.teacher_agent import TeacherAgent

load_dotenv_from_project()

app = FastAPI(title="FinCoach — Teacher Agent (Vanilla)", version="1.0.0")
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# In-memory session store (swap for Redis in production)
sessions: dict[str, dict] = {}


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
    Client polls /api/lesson-status/{session_id} for completion.
    """
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "profile": profile.model_dump(),
        "status": "generating",
        "lesson": None,
        "error": None,
        "generation_log": [],
        "available_steps": 0,
        "total_steps": 0,
    }

    # Fire off lesson generation in background
    import asyncio
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

    try:
        lesson = await teacher.generate_lesson(
            topic=profile.topic,
            audience_level=profile.audience_level,
            proficiency=profile.proficiency,
            student_name=profile.name,
            age=profile.age,
            progress_events=log,
            on_partial=on_partial,
        )
        sessions[session_id]["lesson"] = lesson
        sessions[session_id]["status"] = "ready"
        steps = lesson.get("steps") or []
        sessions[session_id]["available_steps"] = len(steps)
        sessions[session_id]["total_steps"] = len(steps)
    except Exception as e:
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"] = str(e)
        log.append({"kind": "error", "message": str(e)})


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "mode": "vanilla"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
