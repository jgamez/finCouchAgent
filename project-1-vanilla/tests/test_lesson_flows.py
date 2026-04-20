"""Lesson flow registry and API wiring (no Claude calls)."""

import os

# `web.app` raises at import if CLAUDE_API_KEY is unset; tests do not call the API.
if not os.environ.get("CLAUDE_API_KEY"):
    os.environ["CLAUDE_API_KEY"] = (
        "sk-ant-api03-testdummy00000000000000000000000000000000000000000000"
    )

import pytest
from fastapi.testclient import TestClient

from agent.lesson_flows.moneylingo_outline import (
    MONEYLINGO_V1_FLOW_BLOCK_IDS,
    apply_moneylingo_v1_flow_block_ids,
    build_moneylingo_v1_prefetched_outline,
)
from agent.lesson_flows.registry import (
    get_lesson_flow_handler,
    is_valid_flow_id,
    list_lesson_flows,
)


def test_list_flows_contains_default_and_moneylingo():
    ids = {m.id for m in list_lesson_flows()}
    assert "default" in ids
    assert "moneylingo_v1" in ids


def test_is_valid_flow_id():
    assert is_valid_flow_id("default") is True
    assert is_valid_flow_id("moneylingo_v1") is True
    assert is_valid_flow_id("nope") is False


def test_get_handler_unknown():
    with pytest.raises(KeyError):
        get_lesson_flow_handler("unknown_flow")


def test_api_lesson_flows_endpoint():
    from web.app import app

    client = TestClient(app)
    r = client.get("/api/lesson-flows")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(x.get("id") == "default" for x in data)
    assert any(x.get("id") == "moneylingo_v1" for x in data)


def test_moneylingo_prefetched_outline_is_eight_steps():
    o = build_moneylingo_v1_prefetched_outline(
        topic="credit",
        audience_level="high_school",
        proficiency="beginner",
    )
    steps = o.get("steps") or []
    assert len(steps) == 8
    assert steps[0]["step_type"] == "intro"
    assert steps[1]["step_type"] == "video"


def test_apply_moneylingo_flow_block_ids():
    lesson = {
        "steps": [
            {"step_number": 1, "title": "A"},
            {"step_number": 2, "title": "B"},
        ]
    }
    apply_moneylingo_v1_flow_block_ids(lesson)
    assert lesson["steps"][0]["flow_block_id"] == MONEYLINGO_V1_FLOW_BLOCK_IDS[0]
    assert lesson["steps"][1]["flow_block_id"] == MONEYLINGO_V1_FLOW_BLOCK_IDS[1]


def test_prefetched_outline_includes_flow_block_ids():
    o = build_moneylingo_v1_prefetched_outline(
        topic="credit",
        audience_level="high_school",
        proficiency="beginner",
    )
    assert o["steps"][0].get("flow_block_id") == "hook"
    assert o["steps"][-1].get("flow_block_id") == "irl"


def test_try_shell_copies_flow_block_id_from_outline():
    from agent.teacher_agent import TeacherAgent

    outline = build_moneylingo_v1_prefetched_outline(
        topic="saving",
        audience_level="high_school",
        proficiency="intermediate",
    )
    built = TeacherAgent._try_shell_from_outline(outline, min_steps=8, max_steps=8)
    assert built is not None
    shell, n = built
    assert n == 8
    assert shell["steps"][2].get("flow_block_id") == "core_lesson"


def test_start_lesson_rejects_invalid_flow():
    from web.app import app

    client = TestClient(app)
    body = {
        "name": "Test",
        "age": 16,
        "audience_level": "high_school",
        "proficiency": "beginner",
        "topic": "budgeting",
        "lesson_flow_id": "not_a_real_flow",
    }
    r = client.post("/api/start-lesson", json=body)
    assert r.status_code == 422


def test_lesson_sse_unknown_session_returns_404():
    from web.app import app

    client = TestClient(app)
    r = client.get("/api/lesson/00000000-0000-4000-8000-000000000000/events")
    assert r.status_code == 404
