"""
Code-defined MoneyLingo v1 lesson skeleton.

Derived from ``MoneyLingoLessonTemplate-v1.pdf`` at authoring time — not interpreted
from the PDF at runtime. Step order and types are fixed here so UI and MCP usage match
the template (with an extra early video step to satisfy global FinCoach video rules).
"""

from __future__ import annotations

# One block id per prefetched step (8 steps: 7 MoneyLingo blocks + supportive video).
MONEYLINGO_V1_FLOW_BLOCK_IDS: tuple[str, ...] = (
    "hook",
    "context_video",
    "core_lesson",
    "aha_moment",
    "word_wallet",
    "quiz",
    "simulation",
    "irl",
)


def build_moneylingo_v1_prefetched_outline(
    *,
    topic: str,
    audience_level: str,
    proficiency: str,
) -> dict:
    """Return outline JSON consumed by ``_try_shell_from_outline`` (exactly 8 steps)."""
    title_topic = (topic or "your topic").strip()
    lesson = {
        "lesson_title": f"MoneyLingo: {title_topic.title()}",
        "topic": topic,
        "audience_level": audience_level,
        "proficiency": proficiency,
        "estimated_minutes": 40,
        "learning_objectives": [
            "Understand the core money idea in plain language",
            "See real numbers that make the concept click",
            "Leave with three concrete actions you can take",
        ],
        "completion_message": "Great work — you’ve completed this MoneyLingo lesson.",
        "steps": [
            {
                "step_number": 1,
                "step_type": "intro",
                "title": "Hook — curiosity before definitions",
            },
            {
                "step_number": 2,
                "step_type": "video",
                "title": "See it in context (short video)",
            },
            {
                "step_number": 3,
                "step_type": "content",
                "title": "Core lesson — definition and how it works",
            },
            {
                "step_number": 4,
                "step_type": "content",
                "title": "Aha moment — numbers that tell the story",
            },
            {
                "step_number": 5,
                "step_type": "content",
                "title": "Word wallet — key terms",
            },
            {
                "step_number": 6,
                "step_type": "quiz",
                "title": "Quiz — check your understanding",
            },
            {
                "step_number": 7,
                "step_type": "game",
                "title": "Simulation — try a choice",
            },
            {
                "step_number": 8,
                "step_type": "content",
                "title": "In real life — three moves to make",
            },
        ],
    }
    return apply_moneylingo_v1_flow_block_ids(lesson)


def apply_moneylingo_v1_flow_block_ids(lesson: dict) -> dict:
    """
    Annotate each step with ``flow_block_id`` for the lesson UI (code-defined order).
    The web client maps each id to a graphic + label in ``lesson.html`` (extend there when
    ``MONEYLINGO_V1_FLOW_BLOCK_IDS`` gains a new block).
    """
    steps = lesson.get("steps")
    if not isinstance(steps, list):
        return lesson
    ids = MONEYLINGO_V1_FLOW_BLOCK_IDS
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        if i < len(ids):
            step["flow_block_id"] = ids[i]
    return lesson
