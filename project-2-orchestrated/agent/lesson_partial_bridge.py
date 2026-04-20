"""
Bridges progressive lesson generation (inside LangGraph nodes) to the web session store.

The FastAPI app registers an async callback per session_id before running the graph;
build_lesson_node calls emit_partial(...) so the UI can poll partial lessons and logs
while the graph node is still running (astream only yields after each node completes).
"""

from __future__ import annotations

import copy
from typing import Any, Awaitable, Callable, Optional

PartialCallback = Callable[[dict, int, int, Optional[dict]], Awaitable[None]]

_hooks: dict[str, PartialCallback] = {}


def register_partial_callback(session_id: str, cb: PartialCallback) -> None:
    _hooks[session_id] = cb


def unregister_partial_callback(session_id: str) -> None:
    _hooks.pop(session_id, None)


async def emit_partial(
    session_id: Optional[str],
    lesson: dict[str, Any],
    available: int,
    total: int,
    log_entry: Optional[dict] = None,
) -> None:
    if not session_id:
        return
    cb = _hooks.get(session_id)
    if cb:
        await cb(copy.deepcopy(lesson), available, total, log_entry)
