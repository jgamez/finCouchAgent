"""FinCoach default lesson generation (legacy behavior, decoupled from TeacherAgent entrypoint)."""

from __future__ import annotations

from typing import Any, Callable, Optional

from agent.mcp_client import get_mcp_client
from agent.prompts import build_system_prompt, lesson_outline_before_tools_user


async def run_default_lesson(
    teacher: Any,
    *,
    topic: str,
    audience_level: str,
    proficiency: str,
    student_name: str = "",
    age: int | None = None,
    progress_events: list | None = None,
    on_partial: Optional[Callable[[dict, int, int], Any]] = None,
) -> dict:
    system_prompt = build_system_prompt(
        audience_level=audience_level,
        proficiency=proficiency,
        student_name=student_name,
        age=age,
    )

    teacher._append_progress(
        progress_events,
        "start",
        f"Starting lesson for topic {topic!r} ({audience_level}, {proficiency})",
    )

    age_s = str(age) if age is not None else "unknown"

    teacher._append_progress(
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
    outline_resp = await teacher.client.messages.create(
        model=teacher.model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": outline_user}],
    )
    early_outline = teacher._extract_json(outline_resp.content)
    early_shell = teacher._try_shell_from_outline(early_outline)
    if early_shell is not None:
        shell, n_early = early_shell
        await teacher._emit_partial(on_partial, shell, 0, n_early)
        teacher._append_progress(
            progress_events,
            "step",
            f"Lesson structure ready ({n_early} steps). Loading standards and expanding steps…",
        )
    else:
        teacher._append_progress(
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
            teacher._append_progress(
                progress_events,
                "tool_call",
                "fetch_jumpstart_topic (standards context for all steps)",
                tool="fetch_jumpstart_topic",
            )
            jumpstart = await mcp.fetch_jumpstart_topic(topic)
            lesson = await teacher._expand_lesson_steps_targeted_mcp(
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
                teacher._append_progress(
                    progress_events,
                    "model",
                    f"Turn {turn}: calling the model (tools enabled)…",
                    turn=turn,
                )

                response = await teacher.client.messages.create(
                    model=teacher.model,
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
                            teacher._append_progress(
                                progress_events,
                                "assistant_text",
                                f"Model message: {preview}",
                            )
                    elif btype == "tool_use":
                        name = getattr(block, "name", "?")
                        inp = getattr(block, "input", {}) or {}
                        teacher._append_progress(
                            progress_events,
                            "tool_call",
                            teacher._tool_input_line(name, inp),
                            tool=name,
                        )

                teacher._append_progress(
                    progress_events,
                    "model_done",
                    f"Turn {turn} complete — stop_reason={response.stop_reason!r}",
                    stop_reason=response.stop_reason,
                )

                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "end_turn":
                    teacher._append_progress(
                        progress_events,
                        "parse",
                        "Building lesson steps from library content…",
                    )
                    break

                if response.stop_reason == "tool_use":
                    tool_results = await teacher._execute_tool_calls(
                        response.content, mcp, progress_events
                    )
                    messages.append({"role": "user", "content": tool_results})
                    teacher._append_progress(
                        progress_events,
                        "tools_returned",
                        f"Sent {len(tool_results)} tool result(s) back to the model",
                    )
                    continue

                teacher._append_progress(
                    progress_events,
                    "warn",
                    f"Unexpected stop_reason {response.stop_reason!r}; stopping loop",
                )
                break

            lesson = await teacher._build_lesson_after_tools(
                messages=messages,
                system_prompt=system_prompt,
                progress_events=progress_events,
                on_partial=on_partial,
                prefetched_outline=None,
                already_emitted_shell=False,
            )

        steps_n = len(lesson.get("steps", [])) if isinstance(lesson, dict) else 0
        teacher._append_progress(
            progress_events,
            "complete",
            f"Lesson ready with {steps_n} step(s).",
            steps=steps_n,
        )
        return lesson
