"""
Project 2 — Orchestrated Teacher Agent Web App
FastAPI application using LangGraph for agent orchestration.
"""

import os
import uuid
import asyncio

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

from agent.graph import lesson_graph, assessment_graph
from agent.state import TeacherAgentState
from agent.lesson_partial_bridge import (
    register_partial_callback,
    unregister_partial_callback,
)

load_dotenv()

app = FastAPI(title="FinCoach — Teacher Agent (LangGraph)", version="2.0.0")
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# Session store (swap for Redis / DB in production)
sessions: dict[str, dict] = {}


# ─── Request Models ───────────────────────────────────────────────────────────

class StudentProfile(BaseModel):
    name: str
    age: int
    audience_level: str
    proficiency: str
    topic: str


class AssessmentSubmission(BaseModel):
    session_id: str
    answers: list[dict]


# ─── Pages ────────────────────────────────────────────────────────────────────

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


# ─── API ──────────────────────────────────────────────────────────────────────

@app.post("/api/start-lesson")
async def start_lesson(profile: StudentProfile):
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "profile": profile.model_dump(),
        "status": "generating",
        "lesson": None,
        "error": None,
        "graph_state": None,
        "generation_log": [],
        "available_steps": 0,
        "total_steps": 0,
    }

    asyncio.create_task(_run_lesson_graph(session_id, profile))
    return {"session_id": session_id, "status": "generating"}


@app.get("/api/lesson-status/{session_id}")
async def lesson_status(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    log = session.get("generation_log") or []
    phase = log[-1]["message"] if log else session.get("phase", "")
    if not phase:
        phase = "Generating lesson…"
    st = session["status"]
    return {
        "status": st,
        "lesson": session.get("lesson") if st in ("partial", "ready") else None,
        "available_steps": session.get("available_steps", 0),
        "total_steps": session.get("total_steps", 0),
        "error": session.get("error"),
        "phase": phase,
        "generation_log": log,
    }


@app.get("/api/lesson/{session_id}")
async def get_lesson(session_id: str):
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

    # Feed student answers into the assessment graph
    gs = dict(session.get("graph_state") or {})
    if "generation_log" not in gs:
        gs["generation_log"] = []
    state: TeacherAgentState = {
        **gs,
        "student_answers": submission.answers,
        "current_phase": "assessing",
    }

    result = await assessment_graph.ainvoke(state)
    sessions[submission.session_id]["assessment_result"] = result.get("assessment_result")
    return result.get("assessment_result", {})


@app.get("/api/assessment-result/{session_id}")
async def get_assessment_result(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get("assessment_result", {})


@app.get("/api/graph-trace/{session_id}")
async def get_graph_trace(session_id: str):
    """
    Returns the LangGraph execution trace — useful for debugging in Cursor.
    Shows which nodes were executed and the final state at each step.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    state = session.get("graph_state", {})
    return {
        "phases_completed": state.get("messages", []),
        "content_fetched": {
            "articles": len(state.get("fetched_content", [])),
            "videos": len(state.get("fetched_videos", [])),
            "games": len(state.get("fetched_games", [])),
        },
        "lesson_steps": len(state.get("lesson", {}).get("steps", [])) if state.get("lesson") else 0,
        "final_phase": state.get("current_phase"),
    }


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "mode": "langgraph"}


# ─── Background Task ──────────────────────────────────────────────────────────

def _ui_phase_from_state(state: dict) -> str:
    """Short status line for the loading overlay (LangGraph path)."""
    if state.get("lesson"):
        return "Finishing up…"
    if state.get("lesson_error"):
        return "Recovering with fallback lesson…"
    phase = state.get("current_phase") or ""
    if phase == "building":
        return "Building lesson from library content…"
    if phase == "ready":
        return "Almost ready…"
    return "Fetching articles, videos, and games…"


async def _run_lesson_graph(session_id: str, profile: StudentProfile):
    """Runs the LangGraph lesson workflow and updates session state."""
    async def on_partial(
        lesson: dict,
        available: int,
        total: int,
        log_entry: dict | None = None,
    ) -> None:
        sess = sessions[session_id]
        sess["lesson"] = lesson
        sess["available_steps"] = available
        sess["total_steps"] = total
        steps = lesson.get("steps") if isinstance(lesson, dict) else None
        has_outline = isinstance(steps, list) and len(steps) > 0
        if total > 0 and available >= total:
            sess["status"] = "ready"
        elif available >= 1:
            sess["status"] = "partial"
        elif total > 0 and has_outline:
            sess["status"] = "partial"
        else:
            sess["status"] = "generating"
        if log_entry:
            sess.setdefault("generation_log", []).append(log_entry)

    register_partial_callback(session_id, on_partial)
    try:
        initial_state: TeacherAgentState = {
            "session_id": session_id,
            "profile": profile.model_dump(),
            "fetched_content": [],
            "fetched_videos": [],
            "fetched_games": [],
            "jumpstart_content": None,
            "lesson_outline": None,
            "lesson": None,
            "lesson_error": None,
            "student_answers": None,
            "assessment_result": None,
            "current_phase": "fetching",
            "messages": [],
            "generation_log": [],
        }

        sessions[session_id]["phase"] = "Starting lesson workflow…"
        final_state = None

        async for state_update in lesson_graph.astream(
            initial_state, stream_mode="values"
        ):
            final_state = state_update
            log = state_update.get("generation_log") or []
            sessions[session_id]["generation_log"] = list(log)
            sessions[session_id]["phase"] = _ui_phase_from_state(state_update)

        if final_state is None:
            raise RuntimeError("Lesson graph produced no state")

        sessions[session_id]["graph_state"] = final_state
        sessions[session_id]["lesson"] = final_state.get("lesson")
        steps = (final_state.get("lesson") or {}).get("steps") or []
        sessions[session_id]["available_steps"] = len(steps)
        sessions[session_id]["total_steps"] = len(steps)
        sessions[session_id]["status"] = (
            "ready" if final_state.get("lesson") else "error"
        )
        sessions[session_id]["phase"] = final_state.get("current_phase", "")
        sessions[session_id]["error"] = final_state.get("lesson_error")

    except Exception as e:
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"] = str(e)
        log = sessions[session_id].setdefault("generation_log", [])
        log.append({"kind": "error", "message": str(e)})
    finally:
        unregister_partial_callback(session_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8001, reload=True)
