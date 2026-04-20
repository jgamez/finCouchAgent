"""MoneyLingo v1 — code-defined skeleton (from PDF at authoring time) + MCP tools + expansion."""

from __future__ import annotations

from typing import Any, Callable, Optional

from agent.lesson_flows.moneylingo_outline import (
    apply_moneylingo_v1_flow_block_ids,
    build_moneylingo_v1_prefetched_outline,
)
from agent.lesson_flows.moneylingo_prompts import (
    MONEYLINGO_V1_SYSTEM_ADDENDUM,
    moneylingo_v1_initial_user_text,
)
from agent.mcp_client import get_mcp_client
from agent.prompts import build_system_prompt


async def run_moneylingo_v1_lesson(
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
    age_s = str(age) if age is not None else "unknown"

    base_system = build_system_prompt(
        audience_level=audience_level,
        proficiency=proficiency,
        student_name=student_name,
        age=age,
    )
    system_prompt = base_system + "\n" + MONEYLINGO_V1_SYSTEM_ADDENDUM

    teacher._append_progress(
        progress_events,
        "start",
        f"MoneyLingo v1 (code-defined flow) — topic {topic!r} ({audience_level}, {proficiency})",
    )

    seed_text = moneylingo_v1_initial_user_text(
        topic=topic,
        student_name=student_name,
        age_s=age_s,
        audience_level=audience_level,
        proficiency=proficiency,
    )
    messages: list[dict] = [{"role": "user", "content": seed_text}]

    teacher._append_progress(
        progress_events,
        "model",
        "MoneyLingo v1 — tool phase (repository + JumpStart)…",
        turn=0,
    )

    prefetch = build_moneylingo_v1_prefetched_outline(
        topic=topic,
        audience_level=audience_level,
        proficiency=proficiency,
    )

    async with get_mcp_client() as mcp:
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
                    "Expanding MoneyLingo steps from the fixed skeleton…",
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
            prefetched_outline=prefetch,
            already_emitted_shell=False,
            outline_min_steps=8,
            outline_max_steps=8,
        )

        lesson = apply_moneylingo_v1_flow_block_ids(lesson)

        steps_n = len(lesson.get("steps", [])) if isinstance(lesson, dict) else 0
        teacher._append_progress(
            progress_events,
            "complete",
            f"MoneyLingo v1 lesson ready with {steps_n} step(s).",
            steps=steps_n,
        )
        return lesson
