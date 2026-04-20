"""
LangGraph Nodes for the Teacher Agent.

Each node is a pure async function:
  - receives the current state
  - performs one unit of work
  - returns a partial state update (dict)

The graph wires these nodes together with edges and conditional routing.
"""

import asyncio
import copy
import json
import os
from typing import Any

from anthropic import AsyncAnthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from agent.state import TeacherAgentState
from agent.prompts import (
    build_system_prompt,
    ASSESSMENT_GRADING_PROMPT,
    LESSON_OUTLINE_PHASE_USER,
    lesson_expand_step_phase_user,
    lesson_outline_before_tools_user,
    step_expansion_with_library_user,
)
from agent.lesson_partial_bridge import emit_partial
from agent.mcp_client import ContentRepositoryClient, get_mcp_client

client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-opus-4-5"

# Steps 2+ run in parallel within each wave; the next wave starts only after the previous
# one finishes, and results are applied in step order so "Next" always matches readiness.
PARALLEL_STEP_BATCH_SIZE = 2


def _try_shell_from_outline_dict(outline: dict) -> tuple[dict[str, Any], int] | None:
    raw_steps = outline.get("steps") if isinstance(outline, dict) else None
    if not isinstance(raw_steps, list) or len(raw_steps) < 8 or len(raw_steps) > 20:
        return None
    shell: dict[str, Any] = {
        "lesson_title": outline.get("lesson_title", "Lesson"),
        "topic": outline.get("topic", ""),
        "audience_level": outline.get("audience_level", ""),
        "proficiency": outline.get("proficiency", ""),
        "estimated_minutes": outline.get("estimated_minutes", 30),
        "learning_objectives": outline.get("learning_objectives") or [],
        "completion_message": outline.get("completion_message", "Great work!"),
        "steps": [],
    }
    for i, sob in enumerate(raw_steps):
        if not isinstance(sob, dict):
            continue
        shell["steps"].append(
            {
                "step_number": int(sob.get("step_number", i + 1)),
                "step_type": sob.get("step_type", "content"),
                "title": sob.get("title", f"Step {i + 1}"),
                "_pending": True,
            }
        )
    n = len(shell["steps"])
    if n < 8:
        return None
    return shell, n


# ─── Node: outline_lesson (no tools — fast sidebar) ───────────────────────────


async def outline_lesson_node(state: TeacherAgentState) -> dict:
    """Single Claude call: lesson structure only. UI can show sidebar before MCP fetch."""
    profile = state["profile"]
    session_id = state.get("session_id")
    system_prompt = build_system_prompt(
        audience_level=profile["audience_level"],
        proficiency=profile["proficiency"],
        student_name=profile["name"],
        age=profile["age"],
    )
    topic = profile["topic"]
    age_s = str(profile.get("age", "unknown"))
    gen_log = [
        {
            "kind": "model",
            "message": "Planning lesson structure (no tools — fast outline for sidebar)…",
        },
    ]
    outline_user = lesson_outline_before_tools_user(
        topic=topic,
        student_name=profile.get("name") or "",
        age=age_s,
        audience_level=profile["audience_level"],
        proficiency=profile["proficiency"],
    )
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": outline_user}],
    )
    outline = _extract_json(resp.content)
    gen_log.append(
        {
            "kind": "step",
            "message": "Lesson structure ready — fetching library content next…",
        }
    )
    built = _try_shell_from_outline_dict(outline)
    if built is not None and session_id:
        shell, n = built
        await emit_partial(
            session_id,
            copy.deepcopy(shell),
            0,
            n,
            {
                "kind": "step",
                "message": f"Lesson structure ready ({n} steps). Fetching library content…",
            },
        )
    return {
        "lesson_outline": outline,
        "generation_log": gen_log,
        "current_phase": "fetching",
    }


# ─── Node: fetch_content ──────────────────────────────────────────────────────

async def fetch_content_node(state: TeacherAgentState) -> dict:
    """
    JumpStart-only fetch. Text/video/games load per step during build_lesson (targeted MCP).
    Fallback build path bulk-fetches library inside build_lesson_node if needed.
    """
    profile = state["profile"]
    topic = profile["topic"]

    log = [
        {"kind": "step", "message": "Connecting to MCP for JumpStart standards…"},
    ]

    async with get_mcp_client() as mcp:
        jumpstart = await mcp.fetch_jumpstart_topic(topic)

    log.append(
        {
            "kind": "tool_result",
            "message": "JumpStart topic context retrieved (articles/videos/games load per lesson step).",
            "tool": "fetch_jumpstart_topic",
        }
    )

    return {
        "fetched_content": [],
        "fetched_videos": [],
        "fetched_games": [],
        "jumpstart_content": jumpstart if isinstance(jumpstart, dict) else {},
        "current_phase": "building",
        "messages": [{
            "role": "system",
            "content": "JumpStart context loaded; lesson steps will pull text/video/games on demand.",
        }],
        "generation_log": log,
    }


# ─── Node: build_lesson ───────────────────────────────────────────────────────


def _strip_pending_lesson(lesson: dict) -> dict:
    for s in lesson.get("steps") or []:
        if isinstance(s, dict) and "_pending" in s:
            del s["_pending"]
    return lesson


async def _fallback_full_lesson_json(
    _state: TeacherAgentState,
    system_prompt: str,
    messages: list[dict],
    gen_log: list[dict],
    session_id: str | None,
    reason: str,
) -> dict:
    gen_log.append({"kind": "warn", "message": reason})
    messages.append(
        {
            "role": "user",
            "content": (
                "Output the COMPLETE financial education lesson as a single JSON object "
                "following the full schema in your system instructions (all steps with full "
                "content, video/game/assessment objects as required). Use the fetched library "
                "context from the first user message. Return ONLY valid JSON — no markdown fences."
            ),
        }
    )
    response = await client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=system_prompt,
        messages=messages,
    )
    messages.append({"role": "assistant", "content": response.content})
    lesson = _extract_json(response.content)
    if "error" in lesson:
        gen_log.append(
            {
                "kind": "error",
                "message": f"Could not parse lesson JSON: {lesson.get('raw', lesson.get('error', 'unknown'))[:200]}",
            }
        )
        return {
            "lesson_error": lesson.get("raw", "Failed to parse lesson"),
            "current_phase": "error",
            "generation_log": gen_log,
        }
    n_steps = len(lesson.get("steps", []))
    await emit_partial(
        session_id,
        lesson,
        n_steps,
        max(n_steps, 1),
        {
            "kind": "complete",
            "message": f"Lesson JSON ready — {n_steps} step(s), title {lesson.get('lesson_title', '—')!r}.",
            "steps": n_steps,
        },
    )
    gen_log.append(
        {
            "kind": "complete",
            "message": f"Lesson JSON ready — {n_steps} step(s), title {lesson.get('lesson_title', '—')!r}.",
            "steps": n_steps,
        }
    )
    return {
        "lesson": _strip_pending_lesson(lesson),
        "current_phase": "ready",
        "messages": [{"role": "assistant", "content": "Lesson generated successfully."}],
        "generation_log": gen_log,
    }


def _library_kind_for_step_type_nodes(step_type: str) -> str:
    if step_type == "video":
        return "video"
    if step_type == "game":
        return "game"
    return "text"


async def _ensure_library_kind_nodes(
    mcp: Any,
    cache: dict[str, Any],
    kind: str,
    topic: str,
    audience_level: str,
    proficiency: str,
    gen_log: list[dict],
) -> None:
    if kind in cache:
        return
    gen_log.append(
        {
            "kind": "tool_result",
            "message": f"Library fetch: {kind} for step expansion",
            "tool": f"mcp_{kind}",
        }
    )
    if kind == "video":
        cache["video"] = await mcp.get_videos(
            topic, audience_level, proficiency, max_results=5
        )
    elif kind == "game":
        cache["game"] = await mcp.get_games(
            topic, audience_level, proficiency, max_results=12
        )
    else:
        raw = await mcp.search_educational_content(
            topic, audience_level, proficiency, max_results=5
        )
        cache["text"] = raw if isinstance(raw, list) else ([raw] if raw else [])


def _library_json_for_kind_nodes(cache: dict[str, Any], kind: str) -> str:
    if kind == "video":
        return json.dumps({"fetched_videos": cache.get("video", [])}, indent=2)
    if kind == "game":
        return json.dumps({"fetched_games": cache.get("game", [])}, indent=2)
    return json.dumps({"fetched_content": cache.get("text", [])}, indent=2)


async def _targeted_expand_lesson_nodes(
    shell: dict[str, Any],
    n: int,
    outline_dict: dict[str, Any],
    jumpstart: dict[str, Any],
    system_prompt: str,
    gen_log: list[dict],
    session_id: str | None,
    topic: str,
    audience_level: str,
    proficiency: str,
    mcp: Any,
) -> dict[str, Any]:
    outline_json = json.dumps(outline_dict, indent=2)
    jumpstart_json = json.dumps(jumpstart or {}, indent=2)
    lib_cache: dict[str, Any] = {}

    def _finalize_step(
        idx: int,
        sn: int,
        st: str,
        tl: str,
        step_resp_content: list,
    ) -> dict[str, Any]:
        payload = _extract_json(step_resp_content)
        step_obj = None
        if isinstance(payload, dict):
            step_obj = payload.get("step")
            if step_obj is None and payload.get("step_number") is not None:
                step_obj = payload
        if not isinstance(step_obj, dict):
            gen_log.append(
                {
                    "kind": "warn",
                    "message": f"Could not parse expanded step {idx + 1}; using placeholder.",
                }
            )
            step_obj = {
                "step_number": sn,
                "step_type": st,
                "title": tl,
                "content": "This step could not be generated. Please refresh or start a new lesson.",
            }
        return {**step_obj, "_pending": False}

    sn0 = shell["steps"][0]["step_number"]
    st0 = shell["steps"][0]["step_type"]
    tl0 = shell["steps"][0]["title"]
    k0 = _library_kind_for_step_type_nodes(st0)
    await _ensure_library_kind_nodes(
        mcp, lib_cache, k0, topic, audience_level, proficiency, gen_log
    )
    u0 = step_expansion_with_library_user(
        outline_json,
        jumpstart_json,
        _library_json_for_kind_nodes(lib_cache, k0),
        sn0,
        st0,
        tl0,
    )
    r0 = await client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": u0}],
    )
    shell["steps"][0] = _finalize_step(0, sn0, st0, tl0, r0.content)
    await emit_partial(
        session_id,
        shell,
        1,
        n,
        {
            "kind": "step_ready",
            "message": f"Step 1 of {n} ready: {shell['steps'][0].get('title', '')!r}",
            "available_steps": 1,
            "total_steps": n,
        },
    )
    gen_log.append(
        {
            "kind": "step_ready",
            "message": f"Step 1 of {n} ready: {shell['steps'][0].get('title', '')!r}",
            "available_steps": 1,
            "total_steps": n,
        }
    )

    if n <= 1:
        return shell

    kinds_needed = {
        _library_kind_for_step_type_nodes(shell["steps"][i]["step_type"])
        for i in range(1, n)
    }
    for k in kinds_needed:
        await _ensure_library_kind_nodes(
            mcp, lib_cache, k, topic, audience_level, proficiency, gen_log
        )

    _parallel_sem = asyncio.Semaphore(PARALLEL_STEP_BATCH_SIZE)

    async def _expand_index(i: int) -> tuple[int, dict[str, Any]]:
        sn = shell["steps"][i]["step_number"]
        st = shell["steps"][i]["step_type"]
        tl = shell["steps"][i]["title"]
        ki = _library_kind_for_step_type_nodes(st)
        ui = step_expansion_with_library_user(
            outline_json,
            jumpstart_json,
            _library_json_for_kind_nodes(lib_cache, ki),
            sn,
            st,
            tl,
        )
        try:
            async with _parallel_sem:
                ri = await client.messages.create(
                    model=MODEL,
                    max_tokens=8192,
                    system=system_prompt,
                    messages=[{"role": "user", "content": ui}],
                )
            return i, _finalize_step(i, sn, st, tl, ri.content)
        except BaseException as ex:
            gen_log.append(
                {"kind": "warn", "message": f"Step {i + 1} expansion failed: {ex!r}"}
            )
            return i, {
                "step_number": sn,
                "step_type": st,
                "title": tl,
                "content": "This step could not be generated. Please refresh or start a new lesson.",
                "_pending": False,
            }

    batch_start = 1
    while batch_start < n:
        batch_end = min(batch_start + PARALLEL_STEP_BATCH_SIZE, n)
        batch = list(range(batch_start, batch_end))
        results = await asyncio.gather(*[_expand_index(j) for j in batch])
        for idx, step_obj in sorted(results, key=lambda t: t[0]):
            shell["steps"][idx] = step_obj
            av = sum(
                1
                for s in shell["steps"]
                if isinstance(s, dict) and not s.get("_pending")
            )
            await emit_partial(
                session_id,
                shell,
                av,
                n,
                {
                    "kind": "step_ready",
                    "message": f"Step {idx + 1} of {n} ready: {step_obj.get('title', '')!r}",
                    "available_steps": av,
                    "total_steps": n,
                },
            )
            gen_log.append(
                {
                    "kind": "step_ready",
                    "message": f"Step {idx + 1} of {n} ready: {step_obj.get('title', '')!r}",
                    "available_steps": av,
                    "total_steps": n,
                }
            )
        batch_start = batch_end

    return shell


async def build_lesson_node(state: TeacherAgentState) -> dict:
    """
    With a valid pre-fetch outline: expand steps using targeted MCP (text vs video vs game).
    Otherwise: bulk-fetch library, outline in-thread, then expand from full context.
    """
    profile = state["profile"]
    session_id = state.get("session_id")
    system_prompt = build_system_prompt(
        audience_level=profile["audience_level"],
        proficiency=profile["proficiency"],
        student_name=profile["name"],
        age=profile["age"],
    )
    topic = profile["topic"]
    level = profile["audience_level"]
    prof = profile["proficiency"]
    jumpstart = state.get("jumpstart_content") or {}

    gen_log: list[dict] = [
        {
            "kind": "model",
            "message": "Expanding lesson steps from library content…",
            "turn": 1,
        },
    ]

    lesson_outline = state.get("lesson_outline")
    if lesson_outline is not None and _try_shell_from_outline_dict(lesson_outline) is not None:
        built_pf = _try_shell_from_outline_dict(lesson_outline)
        assert built_pf is not None
        shell, n = built_pf
        shell = copy.deepcopy(shell)
        gen_log.append(
            {
                "kind": "step",
                "message": f"Targeted library fetches per step type ({n} steps)…",
            }
        )
        async with get_mcp_client() as mcp:
            await _targeted_expand_lesson_nodes(
                shell,
                n,
                lesson_outline,
                jumpstart,
                system_prompt,
                gen_log,
                session_id,
                topic,
                level,
                prof,
                mcp,
            )
        gen_log.append(
            {
                "kind": "complete",
                "message": f"Lesson JSON ready — {n} step(s), title {shell.get('lesson_title', '—')!r}.",
                "steps": n,
            }
        )
        return {
            "lesson": _strip_pending_lesson(shell),
            "current_phase": "ready",
            "messages": [{"role": "assistant", "content": "Lesson generated successfully."}],
            "generation_log": gen_log,
        }

    # Fallback: bulk MCP fetch (outline missing/invalid), then prior flow
    async with get_mcp_client() as mcp:
        content, videos, games = await asyncio.gather(
            mcp.search_educational_content(topic, level, prof, max_results=5),
            mcp.get_videos(topic, level, prof, max_results=3),
            mcp.get_games(topic, level, prof, max_results=12),
        )

    context = {
        "topic": topic,
        "student": profile,
        "available_content": content if isinstance(content, list) else [content],
        "available_videos": videos if isinstance(videos, list) else [],
        "available_games": games if isinstance(games, list) else [],
        "jumpstart_standards": jumpstart,
    }

    user_msg = (
        f"Here is all the fetched content for this lesson:\n\n"
        f"{json.dumps(context, indent=2)}\n\n"
        f"Topic: '{topic}'. "
        f"Produce an outline JSON then expand steps as instructed."
    )

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_msg}]
    messages.append({"role": "user", "content": LESSON_OUTLINE_PHASE_USER})
    out_resp = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
    )
    messages.append({"role": "assistant", "content": out_resp.content})
    outline = _extract_json(out_resp.content)
    raw_steps = outline.get("steps") if isinstance(outline, dict) else None

    if (
        not isinstance(outline, dict)
        or not isinstance(raw_steps, list)
        or len(raw_steps) < 8
        or len(raw_steps) > 20
    ):
        return await _fallback_full_lesson_json(
            state,
            system_prompt,
            messages,
            gen_log,
            session_id,
            "Outline missing or invalid step count — falling back to one-shot full lesson JSON.",
        )

    built = _try_shell_from_outline_dict(outline)
    if built is None:
        return await _fallback_full_lesson_json(
            state,
            system_prompt,
            messages,
            gen_log,
            session_id,
            "Outline produced fewer than 8 steps — falling back to one-shot full JSON.",
        )
    shell, n = built
    base_messages = copy.deepcopy(messages)
    gen_log.append(
        {
            "kind": "step",
            "message": f"Lesson outline ready ({n} steps). Expanding step 1, then steps 2–{n} in parallel…",
        }
    )

    def _finalize_step(
        idx: int,
        sn: int,
        st: str,
        tl: str,
        step_resp_content: list,
    ) -> dict[str, Any]:
        payload = _extract_json(step_resp_content)
        step_obj = None
        if isinstance(payload, dict):
            step_obj = payload.get("step")
            if step_obj is None and payload.get("step_number") is not None:
                step_obj = payload
        if not isinstance(step_obj, dict):
            gen_log.append(
                {
                    "kind": "warn",
                    "message": f"Could not parse expanded step {idx + 1}; using placeholder.",
                }
            )
            step_obj = {
                "step_number": sn,
                "step_type": st,
                "title": tl,
                "content": "This step could not be generated. Please refresh or start a new lesson.",
            }
        return {**step_obj, "_pending": False}

    sn0 = shell["steps"][0]["step_number"]
    st0 = shell["steps"][0]["step_type"]
    tl0 = shell["steps"][0]["title"]
    m0 = base_messages + [
        {"role": "user", "content": lesson_expand_step_phase_user(sn0, st0, tl0)}
    ]
    r0 = await client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=system_prompt,
        messages=m0,
    )
    shell["steps"][0] = _finalize_step(0, sn0, st0, tl0, r0.content)
    await emit_partial(
        session_id,
        shell,
        1,
        n,
        {
            "kind": "step_ready",
            "message": f"Step 1 of {n} ready: {shell['steps'][0].get('title', '')!r}",
            "available_steps": 1,
            "total_steps": n,
        },
    )
    gen_log.append(
        {
            "kind": "step_ready",
            "message": f"Step 1 of {n} ready: {shell['steps'][0].get('title', '')!r}",
            "available_steps": 1,
            "total_steps": n,
        }
    )

    if n > 1:
        _parallel_sem = asyncio.Semaphore(PARALLEL_STEP_BATCH_SIZE)

        async def _expand_index(i: int) -> tuple[int, dict[str, Any]]:
            sn = shell["steps"][i]["step_number"]
            st = shell["steps"][i]["step_type"]
            tl = shell["steps"][i]["title"]
            mi = base_messages + [
                {"role": "user", "content": lesson_expand_step_phase_user(sn, st, tl)}
            ]
            try:
                async with _parallel_sem:
                    ri = await client.messages.create(
                        model=MODEL,
                        max_tokens=8192,
                        system=system_prompt,
                        messages=mi,
                    )
                return i, _finalize_step(i, sn, st, tl, ri.content)
            except BaseException as ex:
                gen_log.append(
                    {
                        "kind": "warn",
                        "message": f"Step {i + 1} expansion failed: {ex!r}",
                    }
                )
                return i, {
                    "step_number": sn,
                    "step_type": st,
                    "title": tl,
                    "content": "This step could not be generated. Please refresh or start a new lesson.",
                    "_pending": False,
                }

        batch_start = 1
        while batch_start < n:
            batch_end = min(batch_start + PARALLEL_STEP_BATCH_SIZE, n)
            batch = list(range(batch_start, batch_end))
            results = await asyncio.gather(*[_expand_index(j) for j in batch])
            for idx, step_obj in sorted(results, key=lambda t: t[0]):
                shell["steps"][idx] = step_obj
                av = sum(
                    1
                    for s in shell["steps"]
                    if isinstance(s, dict) and not s.get("_pending")
                )
                await emit_partial(
                    session_id,
                    shell,
                    av,
                    n,
                    {
                        "kind": "step_ready",
                        "message": f"Step {idx + 1} of {n} ready: {step_obj.get('title', '')!r}",
                        "available_steps": av,
                        "total_steps": n,
                    },
                )
                gen_log.append(
                    {
                        "kind": "step_ready",
                        "message": f"Step {idx + 1} of {n} ready: {step_obj.get('title', '')!r}",
                        "available_steps": av,
                        "total_steps": n,
                    }
                )
            batch_start = batch_end

    gen_log.append(
        {
            "kind": "complete",
            "message": f"Lesson JSON ready — {n} step(s), title {shell.get('lesson_title', '—')!r}.",
            "steps": n,
        }
    )

    return {
        "lesson": _strip_pending_lesson(shell),
        "current_phase": "ready",
        "messages": [{"role": "assistant", "content": "Lesson generated successfully."}],
        "generation_log": gen_log,
    }


# ─── Node: grade_assessment ───────────────────────────────────────────────────

async def grade_assessment_node(state: TeacherAgentState) -> dict:
    """
    Grades the student's assessment responses using Claude.
    """
    profile = state["profile"]
    lesson = state.get("lesson", {})
    student_answers = state.get("student_answers", [])

    assessment_steps = [
        step for step in lesson.get("steps", [])
        if step.get("step_type") in ("quiz", "open_question", "challenge")
    ]

    grading_input = {
        "lesson_topic": lesson.get("topic"),
        "audience_level": profile["audience_level"],
        "proficiency": profile["proficiency"],
        "student_name": profile["name"],
        "assessment_steps": assessment_steps,
        "student_answers": student_answers,
    }

    response = await client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=ASSESSMENT_GRADING_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Grade these responses:\n\n{json.dumps(grading_input, indent=2)}",
        }],
    )

    result = _extract_json(response.content)

    return {
        "assessment_result": result,
        "current_phase": "done",
    }


# ─── Node: handle_error ───────────────────────────────────────────────────────

async def handle_error_node(state: TeacherAgentState) -> dict:
    """
    Fallback node if lesson generation fails. Tries a simplified re-generation.
    """
    profile = state["profile"]
    system_prompt = build_system_prompt(
        audience_level=profile["audience_level"],
        proficiency=profile["proficiency"],
        student_name=profile["name"],
        age=profile["age"],
    )

    gen_log = [
        {
            "kind": "step",
            "message": "Primary build failed — running simplified fallback lesson generation (no MCP).",
        },
        {
            "kind": "model",
            "message": "Calling Claude for compact fallback lesson JSON…",
            "turn": 1,
        },
    ]

    response = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": (
                f"Generate a simplified 8-step financial education lesson on '{profile['topic']}' "
                f"for a {profile['audience_level']} {profile['proficiency']} student. "
                f"Do not use external content — generate all content yourself. "
                f"Return ONLY valid JSON."
            ),
        }],
    )

    lesson = _extract_json(response.content)
    gen_log.append(
        {
            "kind": "complete",
            "message": f"Fallback lesson generated ({len(lesson.get('steps', []))} steps).",
        }
    )
    return {
        "lesson": lesson,
        "lesson_error": None,
        "current_phase": "ready",
        "generation_log": gen_log,
    }


# ─── Routing Functions ────────────────────────────────────────────────────────

def route_after_build(state: TeacherAgentState) -> str:
    """Route after lesson build: success → ready, error → handle_error."""
    if state.get("lesson_error") or state.get("current_phase") == "error":
        return "handle_error"
    return "ready"


def route_for_assessment(state: TeacherAgentState) -> str:
    """Route based on whether student answers are present."""
    if state.get("student_answers"):
        return "grade"
    return "wait"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _extract_json(content: list) -> dict:
    for block in content:
        if hasattr(block, "text"):
            return _parse_json_text(block.text)
    return {"error": "No text content in response"}


def _parse_json_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return {"error": "JSON parse failed", "raw": text[:500]}
