"""
Integration tests against the Anthropic Messages API.

Run from project-1-vanilla (network required):

  CLAUDE_API_KEY=sk-ant-... pytest tests/test_claude_api.py -v

Or rely on .env in this directory. Tests skip if CLAUDE_API_KEY is unset.
"""

from __future__ import annotations

import os

import httpx
import pytest
import anthropic

from agent.anthropic_env import (
    anthropic_base_url,
    claude_api_key,
    claude_messages_url,
    default_request_headers,
    load_dotenv_from_project,
)

# Small model for auth + connectivity (override with CLAUDE_TEST_MODEL if needed).
_DEFAULT_TEST_MODEL = "claude-haiku-4-5"

_PLACEHOLDER_KEYS = frozenset(
    {
        "your_claude_api_key_here",
        "your_anthropic_api_key_here",
    }
)


@pytest.fixture(scope="module", autouse=True)
def _load_env():
    load_dotenv_from_project()


@pytest.fixture(scope="module")
def api_key() -> str:
    key = claude_api_key()
    if not key:
        pytest.skip("Set CLAUDE_API_KEY in .env (or env) to run API tests")
    if key.strip().lower() in _PLACEHOLDER_KEYS:
        pytest.skip(
            "CLAUDE_API_KEY is still a placeholder; set a real key from "
            "https://console.anthropic.com/settings/keys"
        )
    return key


@pytest.fixture(scope="module")
def messages_url() -> str:
    return claude_messages_url()


@pytest.fixture(scope="module")
def test_model() -> str:
    return os.getenv("CLAUDE_TEST_MODEL", _DEFAULT_TEST_MODEL).strip()


def test_claude_messages_via_anthropic_sdk(api_key, messages_url, test_model):
    """Smoke test using the official client (same shape as TeacherAgent)."""
    headers = default_request_headers(api_key)
    # trust_env=False avoids broken HTTP(S)_PROXY entries (common source of 403 / connection errors).
    with httpx.Client(timeout=60.0, trust_env=False) as http:
        client = anthropic.Anthropic(
            api_key=api_key,
            base_url=anthropic_base_url(messages_url),
            default_headers={
                k: v for k, v in headers.items() if k.lower() != "x-api-key" and v
            },
            http_client=http,
        )
        try:
            msg = client.messages.create(
                model=test_model,
                max_tokens=32,
                messages=[{"role": "user", "content": 'Reply with exactly the word "pong".'}],
            )
        except anthropic.AuthenticationError as e:
            pytest.fail(
                "Anthropic rejected the API key (401). Use a key from "
                "https://console.anthropic.com/settings/keys — not Cursor/Claude Code keys. "
                f"Detail: {e}"
            )
    texts: list[str] = []
    for block in msg.content:
        if getattr(block, "type", None) != "text":
            continue
        t = getattr(block, "text", None)
        if isinstance(t, str):
            texts.append(t)
    assert texts, f"Expected text content, got: {msg.content}"
    assert "pong" in texts[0].lower()


def test_claude_messages_via_raw_http(api_key, messages_url, test_model):
    """
    Same request as plain HTTP + HEADERS (matches typical curl / other-project style).
    Helps isolate SDK vs key / URL / proxy issues.
    """
    url = messages_url
    headers = default_request_headers(api_key)
    payload = {
        "model": test_model,
        "max_tokens": 32,
        "messages": [{"role": "user", "content": 'Reply with exactly the word "pong".'}],
    }
    with httpx.Client(timeout=60.0, trust_env=False) as client:
        r = client.post(url, json=payload, headers=headers)
    if r.status_code == 401:
        pytest.fail(
            "401 invalid x-api-key: key is missing, wrong, or not an Anthropic console key. "
            f"Body: {r.text[:500]}"
        )
    r.raise_for_status()
    data = r.json()
    content = data.get("content") or []
    texts = [
        c.get("text", "")
        for c in content
        if isinstance(c, dict) and c.get("type") == "text"
    ]
    assert texts, f"Unexpected response: {data!r:.500}"
    assert "pong" in texts[0].lower()
