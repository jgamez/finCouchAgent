"""Lesson flow ids, labels, and handler resolution."""

from __future__ import annotations

from dataclasses import dataclass

from agent.lesson_flows.context import LessonFlowHandler


@dataclass(frozen=True)
class LessonFlowMeta:
    id: str
    label: str
    description: str


_FLOW_ORDER: list[LessonFlowMeta] = [
    LessonFlowMeta(
        id="default",
        label="FinCoach (default)",
        description="Current production lesson flow: outline, MCP tools, and step expansion.",
    ),
    LessonFlowMeta(
        id="moneylingo_v1",
        label="MoneyLingo v1",
        description="Code-defined MoneyLingo v1 flow (8-step skeleton from template + MCP tools).",
    ),
]

_ID_TO_META = {m.id: m for m in _FLOW_ORDER}


def list_lesson_flows() -> list[LessonFlowMeta]:
    return list(_FLOW_ORDER)


def is_valid_flow_id(flow_id: str) -> bool:
    return flow_id in _ID_TO_META


def get_lesson_flow_handler(flow_id: str) -> LessonFlowHandler:
    if flow_id == "default":
        from agent.lesson_flows import default_flow

        return default_flow.run_default_lesson
    if flow_id == "moneylingo_v1":
        from agent.lesson_flows import moneylingo_v1

        return moneylingo_v1.run_moneylingo_v1_lesson
    raise KeyError(f"Unknown lesson_flow_id: {flow_id!r}")
