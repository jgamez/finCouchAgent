"""
Typing port for lesson flows.

Flows receive a ``TeacherAgent`` instance as the first argument; this Protocol
documents the surface they rely on so future refactors can swap implementations.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional, Protocol, runtime_checkable

# ``teacher`` is the concrete ``TeacherAgent``; kept as ``Any`` at call sites to avoid cycles.
LessonFlowHandler = Callable[..., Awaitable[dict]]


@runtime_checkable
class LessonFlowTeacherPort(Protocol):
    """Minimal attributes lesson flows read from the teacher agent."""

    client: Any
    model: str

    def _append_progress(
        self, progress_events: list | None, kind: str, message: str, **extra: Any
    ) -> None: ...

    async def _emit_partial(
        self,
        cb: Optional[Callable[..., Any]],
        lesson: dict,
        available: int,
        total: int,
    ) -> None: ...

    def _extract_json(self, content: list) -> dict: ...

    def _try_shell_from_outline(self, outline: dict, **kwargs: Any) -> Any: ...

    async def _expand_lesson_steps_targeted_mcp(self, **kwargs: Any) -> dict: ...

    async def _build_lesson_after_tools(self, **kwargs: Any) -> dict: ...

    async def _execute_tool_calls(
        self, content: list, mcp: Any, progress_events: list | None = None
    ) -> list[dict]: ...

    def _tool_input_line(self, tool_name: str, tool_input: dict) -> str: ...
