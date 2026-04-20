"""Tests for free-form financial topic heuristics."""

import os

if not os.environ.get("CLAUDE_API_KEY"):
    os.environ["CLAUDE_API_KEY"] = (
        "sk-ant-api03-testdummy00000000000000000000000000000000000000000000"
    )

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent.topic_financial import PRESET_TOPICS, is_financial_education_topic


def test_presets_all_accepted():
    for t in PRESET_TOPICS:
        assert is_financial_education_topic(t) is True


def test_rejects_obvious_non_finance():
    assert is_financial_education_topic("dinosaurs in the cretaceous") is False
    assert is_financial_education_topic("how to play chess") is False
    assert is_financial_education_topic("a") is False
    assert is_financial_education_topic("") is False


def test_accepts_relevant_phrases():
    assert is_financial_education_topic("Help me plan my retirement savings") is True
    assert is_financial_education_topic("saving for college in two years") is True
    assert is_financial_education_topic("credit cards and fico") is True


def test_accepts_short_instrument_abbreviations():
    assert is_financial_education_topic("ETF") is True
    assert is_financial_education_topic("etf") is True
    assert is_financial_education_topic("HSA") is True
    assert is_financial_education_topic("IRAs") is True
    assert is_financial_education_topic("IRAs and taxes") is True


def test_start_lesson_api_rejects_non_financial_freeform():
    from web.app import app

    client = TestClient(app)
    r = client.post(
        "/api/start-lesson",
        json={
            "name": "A",
            "age": 16,
            "audience_level": "high_school",
            "proficiency": "advanced",
            "topic": "volcanoes and plate tectonics for science class",
            "lesson_flow_id": "default",
        },
    )
    assert r.status_code == 422


def test_student_profile_freeform_finance_validates():
    from web.app import StudentProfile

    StudentProfile(
        name="A",
        age=16,
        audience_level="high_school",
        proficiency="advanced",
        topic="saving for my first car",
        lesson_flow_id="default",
    )
    with pytest.raises(ValidationError) as e:
        StudentProfile(
            name="A",
            age=16,
            audience_level="high_school",
            proficiency="advanced",
            topic="basketball coaching basics",
            lesson_flow_id="default",
        )
    err = str(e.value).lower()
    assert "financial" in err or "choose" in err
