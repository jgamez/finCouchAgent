"""
Teacher Agent — Vanilla Anthropic SDK implementation.

This is a manual agentic loop:
  1. Claude receives the student profile + task
  2. Claude decides to call MCP tools (content, videos, games, jumpstart)
  3. We execute the tool calls and return results to Claude
  4. Claude builds the final lesson JSON
  5. We parse and return the structured lesson

No orchestration framework — just the Anthropic Python SDK.
"""

import copy
import json
import asyncio
from typing import Any, AsyncGenerator, Awaitable, Callable, Mapping, Optional

import anthropic

from agent.mcp_client import ContentRepositoryClient, get_mcp_client
from agent.prompts import (
    build_system_prompt,
    ASSESSMENT_GRADING_PROMPT,
    LESSON_OUTLINE_PHASE_USER,
    lesson_expand_step_phase_user,
    lesson_outline_before_tools_user,
    step_expansion_with_library_user,
)

# Steps 2+ run in parallel within each wave; the next wave starts only after the previous
# one finishes, and results are applied in step order so "Next" always matches readiness.
PARALLEL_STEP_BATCH_SIZE = 2


class TeacherAgent:
    """
    Orchestrates the lesson generation flow using the Anthropic API
    with a manual tool-use loop connected to the MCP content server.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
    ):
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            default_headers=default_headers,
        )
        self.model = "claude-opus-4-5"

    @staticmethod
    def _append_progress(
        progress_events: list | None, kind: str, message: str, **extra: Any
    ) -> None:
        if progress_events is None:
            return
        row = {"kind": kind, "message": message, **extra}
        progress_events.append(row)

    @staticmethod
    def _tool_input_line(tool_name: str, tool_input: dict) -> str:
        parts = []
        if tool_input.get("topic"):
            parts.append(f"topic={tool_input['topic']!r}")
        if tool_input.get("audience_level"):
            parts.append(f"audience={tool_input['audience_level']}")
        if tool_input.get("proficiency"):
            parts.append(f"proficiency={tool_input['proficiency']}")
        if tool_input.get("max_results") is not None:
            parts.append(f"max_results={tool_input['max_results']}")
        inner = ", ".join(parts) if parts else "—"
        return f"{tool_name}({inner})"

    @staticmethod
    def _tool_result_line(tool_name: str, result: Any) -> str:
        if isinstance(result, list):
            return f"{tool_name} returned {len(result)} item(s)"
        if isinstance(result, dict):
            keys = list(result.keys())[:6]
            return f"{tool_name} returned data ({len(result)} keys: {', '.join(keys)}{'…' if len(result) > 6 else ''})"
        if isinstance(result, str):
            if result.startswith("Error") or "error" in result[:20].lower():
                return f"{tool_name}: {result[:120]}{'…' if len(result) > 120 else ''}"
            return f"{tool_name} returned text ({len(result)} characters)"
        return f"{tool_name} completed"

    @staticmethod
    async def _emit_partial(
        cb: Optional[Callable[[dict, int, int], Any]],
        lesson: dict,
        available: int,
        total: int,
    ) -> None:
        if cb is None:
            return
        res = cb(copy.deepcopy(lesson), available, total)
        if asyncio.iscoroutine(res):
            await res

    async def generate_lesson(
        self,
        topic: str,
        audience_level: str,
        proficiency: str,
        student_name: str = "",
        age: int = None,
        progress_events: list | None = None,
        on_partial: Optional[Callable[[dict, int, int], Any]] = None,
    ) -> dict:
        """
        Full agentic loop to generate a structured lesson.
        Returns a parsed lesson dict.
        """
        system_prompt = build_system_prompt(
            audience_level=audience_level,
            proficiency=proficiency,
            student_name=student_name,
            age=age,
        )

        self._append_progress(
            progress_events,
            "start",
            f"Starting lesson for topic {topic!r} ({audience_level}, {proficiency})",
        )

        age_s = str(age) if age is not None else "unknown"

        self._append_progress(
            progress_events,
            "model",
            "Planning lesson structure (no tools — fast outline for sidebar)…",
            turn=0,
        )
        outline_user = lesson_outline_before_tools_user(
            topic=topic,
            student_name=student_name or "",
            age=age_s,
            audience_level=audience_level,
            proficiency=proficiency,
        )
        outline_resp = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": outline_user}],
        )
        early_outline = self._extract_json(outline_resp.content)
        early_shell = self._try_shell_from_outline(early_outline)
        if early_shell is not None:
            shell, n_early = early_shell
            await self._emit_partial(on_partial, shell, 0, n_early)
            self._append_progress(
                progress_events,
                "step",
                f"Lesson structure ready ({n_early} steps). Loading standards and expanding steps…",
            )
        else:
            self._append_progress(
                progress_events,
                "warn",
                "Pre-tool outline was invalid — fetching with tools first, then outline in-thread.",
            )
            user_message = (
                f"Generate a complete financial education lesson on the topic: '{topic}'. "
                f"Student: {student_name or 'Anonymous'}, age {age_s}, "
                f"{audience_level.replace('_', ' ')} level, {proficiency} proficiency. "
                f"First use the available tools to fetch relevant content, videos, and games "
                f"from the content repository and JumpStart.org. Then build the full lesson JSON."
            )
            messages = [{"role": "user", "content": user_message}]

        async with get_mcp_client() as mcp:
            if early_shell is not None:
                shell, n_early = early_shell
                self._append_progress(
                    progress_events,
                    "tool_call",
                    "fetch_jumpstart_topic (standards context for all steps)",
                    tool="fetch_jumpstart_topic",
                )
                jumpstart = await mcp.fetch_jumpstart_topic(topic)
                lesson = await self._expand_lesson_steps_targeted_mcp(
                    mcp=mcp,
                    shell=shell,
                    n=n_early,
                    outline_dict=early_outline,
                    jumpstart=jumpstart if isinstance(jumpstart, dict) else {},
                    system_prompt=system_prompt,
                    progress_events=progress_events,
                    on_partial=on_partial,
                    topic=topic,
                    audience_level=audience_level,
                    proficiency=proficiency,
                )
            else:
                tools = mcp.as_anthropic_tools()
                turn = 0
                while True:
                    turn += 1
                    self._append_progress(
                        progress_events,
                        "model",
                        f"Turn {turn}: calling the model (tools enabled)…",
                        turn=turn,
                    )

                    response = await self.client.messages.create(
                        model=self.model,
                        max_tokens=8192,
                        system=system_prompt,
                        tools=tools,
                        messages=messages,
                    )

                    for block in response.content:
                        btype = getattr(block, "type", None)
                        if btype == "text":
                            snippet = (getattr(block, "text", "") or "").strip()
                            if snippet:
                                preview = snippet[:160] + ("…" if len(snippet) > 160 else "")
                                self._append_progress(
                                    progress_events,
                                    "assistant_text",
                                    f"Model message: {preview}",
                                )
                        elif btype == "tool_use":
                            name = getattr(block, "name", "?")
                            inp = getattr(block, "input", {}) or {}
                            self._append_progress(
                                progress_events,
                                "tool_call",
                                self._tool_input_line(name, inp),
                                tool=name,
                            )

                    self._append_progress(
                        progress_events,
                        "model_done",
                        f"Turn {turn} complete — stop_reason={response.stop_reason!r}",
                        stop_reason=response.stop_reason,
                    )

                    messages.append({"role": "assistant", "content": response.content})

                    if response.stop_reason == "end_turn":
                        self._append_progress(
                            progress_events,
                            "parse",
                            "Building lesson steps from library content…",
                        )
                        break

                    if response.stop_reason == "tool_use":
                        tool_results = await self._execute_tool_calls(
                            response.content, mcp, progress_events
                        )
                        messages.append({"role": "user", "content": tool_results})
                        self._append_progress(
                            progress_events,
                            "tools_returned",
                            f"Sent {len(tool_results)} tool result(s) back to the model",
                        )
                        continue

                    self._append_progress(
                        progress_events,
                        "warn",
                        f"Unexpected stop_reason {response.stop_reason!r}; stopping loop",
                    )
                    break

                lesson = await self._build_lesson_after_tools(
                    messages=messages,
                    system_prompt=system_prompt,
                    progress_events=progress_events,
                    on_partial=on_partial,
                    prefetched_outline=None,
                    already_emitted_shell=False,
                )

            steps_n = len(lesson.get("steps", [])) if isinstance(lesson, dict) else 0
            self._append_progress(
                progress_events,
                "complete",
                f"Lesson ready with {steps_n} step(s).",
                steps=steps_n,
            )
            return lesson

    async def generate_lesson_stream(
        self,
        topic: str,
        audience_level: str,
        proficiency: str,
        student_name: str = "",
        age: int = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Streaming version — yields status events during generation.
        Useful for showing a live progress indicator in the UI.
        """
        yield {"event": "status", "message": "Connecting to content library..."}
        await asyncio.sleep(0.1)

        yield {"event": "status", "message": f"Researching '{topic}' content..."}
        lesson = await self.generate_lesson(
            topic, audience_level, proficiency, student_name, age
        )
        yield {"event": "status", "message": "Building your personalized lesson..."}
        yield {"event": "lesson_ready", "lesson": lesson}

    @staticmethod
    def _strip_pending(lesson: dict) -> dict:
        for s in lesson.get("steps") or []:
            if isinstance(s, dict) and "_pending" in s:
                del s["_pending"]
        return lesson

    @staticmethod
    def _try_shell_from_outline(outline: dict) -> Optional[tuple[dict[str, Any], int]]:
        """Return (shell_lesson_dict, n_steps) or None if outline is unusable."""
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

    async def _fallback_full_lesson_json(
        self,
        messages: list,
        system_prompt: str,
        progress_events: list | None,
        on_partial: Optional[Callable[[dict, int, int], Any]],
        reason: str,
    ) -> dict:
        self._append_progress(progress_events, "warn", reason)
        messages.append(
            {
                "role": "user",
                "content": (
                    "Output the COMPLETE financial education lesson as a single JSON object "
                    "following the full schema in your system instructions (all steps with full "
                    "content, video/game/assessment objects as required). Use the tool results "
                    "already in this conversation. Return ONLY valid JSON — no markdown fences."
                ),
            }
        )
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system_prompt,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        lesson = self._extract_lesson(resp.content)
        if not isinstance(lesson, dict):
            lesson = {}
        steps = lesson.get("steps") or []
        tot = len(steps)
        await self._emit_partial(on_partial, lesson, tot, max(tot, 1))
        return self._strip_pending(lesson)

    @staticmethod
    def _library_kind_for_step_type(step_type: str) -> str:
        if step_type == "video":
            return "video"
        if step_type == "game":
            return "game"
        return "text"

    async def _ensure_library_kind(
        self,
        mcp: Any,
        cache: dict[str, Any],
        kind: str,
        topic: str,
        audience_level: str,
        proficiency: str,
        progress_events: list | None,
    ) -> None:
        if kind in cache:
            return
        self._append_progress(
            progress_events,
            "tool_result",
            f"Library fetch: {kind} content for step expansion",
            tool=f"mcp_{kind}",
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

    @staticmethod
    def _library_json_for_kind(cache: dict[str, Any], kind: str) -> str:
        if kind == "video":
            return json.dumps({"fetched_videos": cache.get("video", [])}, indent=2)
        if kind == "game":
            return json.dumps({"fetched_games": cache.get("game", [])}, indent=2)
        return json.dumps({"fetched_content": cache.get("text", [])}, indent=2)

    async def _expand_lesson_steps_targeted_mcp(
        self,
        mcp: Any,
        shell: dict[str, Any],
        n: int,
        outline_dict: dict[str, Any],
        jumpstart: dict[str, Any],
        system_prompt: str,
        progress_events: list | None,
        on_partial: Optional[Callable[[dict, int, int], Any]],
        topic: str,
        audience_level: str,
        proficiency: str,
    ) -> dict:
        """
        Expand each step with a single Claude turn. MCP calls are scoped by step type:
        text steps → search_educational_content only; video → get_videos; game → get_games.
        Fetches are cached so each category runs at most once; step 1 only waits on its category.
        """
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
            payload = self._extract_json(step_resp_content)
            step_obj = None
            if isinstance(payload, dict):
                step_obj = payload.get("step")
                if step_obj is None and payload.get("step_number") is not None:
                    step_obj = payload
            if not isinstance(step_obj, dict):
                self._append_progress(
                    progress_events,
                    "warn",
                    f"Could not parse expanded step {idx + 1}; using placeholder.",
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
        k0 = self._library_kind_for_step_type(st0)
        await self._ensure_library_kind(
            mcp, lib_cache, k0, topic, audience_level, proficiency, progress_events
        )
        u0 = step_expansion_with_library_user(
            outline_json,
            jumpstart_json,
            self._library_json_for_kind(lib_cache, k0),
            sn0,
            st0,
            tl0,
        )
        r0 = await self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": u0}],
        )
        shell["steps"][0] = _finalize_step(0, sn0, st0, tl0, r0.content)
        await self._emit_partial(on_partial, shell, 1, n)
        self._append_progress(
            progress_events,
            "step_ready",
            f"Step 1 of {n} ready: {shell['steps'][0].get('title', '')!r}",
            available_steps=1,
            total_steps=n,
        )

        if n <= 1:
            return self._strip_pending(shell)

        kinds_needed = {
            self._library_kind_for_step_type(shell["steps"][i]["step_type"])
            for i in range(1, n)
        }
        for k in kinds_needed:
            await self._ensure_library_kind(
                mcp, lib_cache, k, topic, audience_level, proficiency, progress_events
            )

        _parallel_sem = asyncio.Semaphore(PARALLEL_STEP_BATCH_SIZE)

        async def _expand_index(i: int) -> tuple[int, dict[str, Any]]:
            sn = shell["steps"][i]["step_number"]
            st = shell["steps"][i]["step_type"]
            tl = shell["steps"][i]["title"]
            ki = self._library_kind_for_step_type(st)
            ui = step_expansion_with_library_user(
                outline_json,
                jumpstart_json,
                self._library_json_for_kind(lib_cache, ki),
                sn,
                st,
                tl,
            )
            try:
                async with _parallel_sem:
                    ri = await self.client.messages.create(
                        model=self.model,
                        max_tokens=8192,
                        system=system_prompt,
                        messages=[{"role": "user", "content": ui}],
                    )
                return i, _finalize_step(i, sn, st, tl, ri.content)
            except BaseException as ex:
                self._append_progress(
                    progress_events,
                    "warn",
                    f"Step {i + 1} expansion failed: {ex!r}",
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
                await self._emit_partial(on_partial, shell, av, n)
                self._append_progress(
                    progress_events,
                    "step_ready",
                    f"Step {idx + 1} of {n} ready: {step_obj.get('title', '')!r}",
                    available_steps=av,
                    total_steps=n,
                )
            batch_start = batch_end

        return self._strip_pending(shell)

    async def _build_lesson_after_tools(
        self,
        messages: list,
        system_prompt: str,
        progress_events: list | None,
        on_partial: Optional[Callable[[dict, int, int], Any]],
        prefetched_outline: Optional[dict[str, Any]] = None,
        already_emitted_shell: bool = False,
    ) -> dict:
        shell: dict[str, Any]
        n: int
        base_messages: list[dict[str, Any]]

        use_prefetch = False
        if prefetched_outline is not None:
            built = self._try_shell_from_outline(prefetched_outline)
            if built is not None:
                shell, n = built
                base_messages = copy.deepcopy(messages)
                use_prefetch = True
                if not already_emitted_shell:
                    await self._emit_partial(on_partial, shell, 0, n)
                self._append_progress(
                    progress_events,
                    "step",
                    f"Using pre-tool outline ({n} steps). Expanding step 1, then steps 2–{n} in parallel…",
                )

        if not use_prefetch:
            messages.append({"role": "user", "content": LESSON_OUTLINE_PHASE_USER})
            out_resp = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": out_resp.content})
            outline = self._extract_json(out_resp.content)
            raw_steps = outline.get("steps") if isinstance(outline, dict) else None
            if (
                not isinstance(outline, dict)
                or not isinstance(raw_steps, list)
                or len(raw_steps) < 8
                or len(raw_steps) > 20
            ):
                return await self._fallback_full_lesson_json(
                    messages,
                    system_prompt,
                    progress_events,
                    on_partial,
                    "Outline missing or invalid step count — falling back to one-shot full lesson JSON.",
                )

            built = self._try_shell_from_outline(outline)
            if built is None:
                return await self._fallback_full_lesson_json(
                    messages,
                    system_prompt,
                    progress_events,
                    on_partial,
                    "Outline produced fewer than 8 steps — falling back to one-shot full JSON.",
                )
            shell, n = built
            base_messages = copy.deepcopy(messages)

        # Snapshot after outline only — parallel expansions reuse this prefix (no growing context).

        if not use_prefetch:
            self._append_progress(
                progress_events,
                "step",
                f"Lesson outline ready ({n} steps). Expanding step 1, then steps 2–{n} in parallel…",
            )

        def _finalize_step(
            idx: int,
            sn: int,
            st: str,
            tl: str,
            step_resp_content: list,
        ) -> dict[str, Any]:
            payload = self._extract_json(step_resp_content)
            step_obj = None
            if isinstance(payload, dict):
                step_obj = payload.get("step")
                if step_obj is None and payload.get("step_number") is not None:
                    step_obj = payload
            if not isinstance(step_obj, dict):
                self._append_progress(
                    progress_events,
                    "warn",
                    f"Could not parse expanded step {idx + 1}; using placeholder.",
                )
                step_obj = {
                    "step_number": sn,
                    "step_type": st,
                    "title": tl,
                    "content": "This step could not be generated. Please refresh or start a new lesson.",
                }
            return {**step_obj, "_pending": False}

        # Step 1 first so the first publish has one full step (sidebar + readable intro).
        sn0 = shell["steps"][0]["step_number"]
        st0 = shell["steps"][0]["step_type"]
        tl0 = shell["steps"][0]["title"]
        m0 = base_messages + [
            {"role": "user", "content": lesson_expand_step_phase_user(sn0, st0, tl0)}
        ]
        r0 = await self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system_prompt,
            messages=m0,
        )
        shell["steps"][0] = _finalize_step(0, sn0, st0, tl0, r0.content)
        await self._emit_partial(on_partial, shell, 1, n)
        self._append_progress(
            progress_events,
            "step_ready",
            f"Step 1 of {n} ready: {shell['steps'][0].get('title', '')!r}",
            available_steps=1,
            total_steps=n,
        )

        if n <= 1:
            return self._strip_pending(shell)

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
                    ri = await self.client.messages.create(
                        model=self.model,
                        max_tokens=8192,
                        system=system_prompt,
                        messages=mi,
                    )
                return i, _finalize_step(i, sn, st, tl, ri.content)
            except BaseException as ex:
                self._append_progress(
                    progress_events,
                    "warn",
                    f"Step {i + 1} expansion failed: {ex!r}",
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
                await self._emit_partial(on_partial, shell, av, n)
                self._append_progress(
                    progress_events,
                    "step_ready",
                    f"Step {idx + 1} of {n} ready: {step_obj.get('title', '')!r}",
                    available_steps=av,
                    total_steps=n,
                )
            batch_start = batch_end

        return self._strip_pending(shell)

    async def grade_assessment(
        self,
        lesson: dict,
        student_answers: list[dict],
        audience_level: str,
        proficiency: str,
    ) -> dict:
        """
        Grade student assessment responses and return detailed feedback.
        """
        # Find assessment steps in the lesson
        assessment_steps = [
            step for step in lesson.get("steps", [])
            if step.get("step_type") in ("quiz", "open_question", "challenge")
        ]

        grading_input = {
            "lesson_topic": lesson.get("topic"),
            "audience_level": audience_level,
            "proficiency": proficiency,
            "assessment_steps": assessment_steps,
            "student_answers": student_answers,
        }

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=ASSESSMENT_GRADING_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Grade these student responses:\n\n{json.dumps(grading_input, indent=2)}",
                }
            ],
        )

        return self._extract_json(response.content)

    async def _execute_tool_calls(
        self,
        content: list,
        mcp: ContentRepositoryClient,
        progress_events: list | None = None,
    ) -> list[dict]:
        """Execute all tool_use blocks in parallel; return tool_result messages in block order."""
        blocks = [b for b in content if getattr(b, "type", None) == "tool_use"]
        if not blocks:
            return []

        async def run_block(block: Any) -> dict:
            tool_name = block.name
            tool_input = block.input
            try:
                result = await self._call_mcp_tool(mcp, tool_name, tool_input)
                self._append_progress(
                    progress_events,
                    "tool_result",
                    self._tool_result_line(tool_name, result),
                    tool=tool_name,
                )
                return {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            except Exception as e:
                self._append_progress(
                    progress_events,
                    "tool_error",
                    f"{tool_name} failed: {e}",
                    tool=tool_name,
                )
                return {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Error: {str(e)}",
                    "is_error": True,
                }

        return list(await asyncio.gather(*(run_block(b) for b in blocks)))

    async def _call_mcp_tool(
        self, mcp: ContentRepositoryClient, tool_name: str, tool_input: dict
    ) -> Any:
        """Dispatch a tool call to the MCP client."""
        if tool_name == "search_educational_content":
            return await mcp.search_educational_content(**tool_input)
        elif tool_name == "get_videos":
            return await mcp.get_videos(**tool_input)
        elif tool_name == "get_games":
            return await mcp.get_games(**tool_input)
        elif tool_name == "fetch_jumpstart_topic":
            return await mcp.fetch_jumpstart_topic(**tool_input)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _extract_lesson(self, content: list) -> dict:
        """Extract and parse the lesson JSON from Claude's final response."""
        for block in content:
            if hasattr(block, "text"):
                return self._extract_json_from_text(block.text)
        return {}

    def _extract_json(self, content: list) -> dict:
        """Extract JSON from any text block in the response."""
        for block in content:
            if hasattr(block, "text"):
                return self._extract_json_from_text(block.text)
        return {}

    def _extract_json_from_text(self, text: str) -> dict:
        """Parse JSON from text, handling markdown code fences."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
        return {"error": "Failed to parse lesson JSON", "raw": text[:500]}
