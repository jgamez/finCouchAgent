"""Env-driven Anthropic API base URL (shared by web app and tests)."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

_DEFAULT_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


def load_dotenv_from_project() -> None:
    """Load project-1-vanilla/.env when cwd may differ (e.g. pytest)."""
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")


def anthropic_base_url(messages_url: str) -> str:
    """SDK expects API origin; CLAUDE_API_URL may point at /v1/messages."""
    p = urlparse(messages_url.strip())
    path = (p.path or "").rstrip("/")
    if path.endswith("/v1/messages"):
        path = path[: -len("/v1/messages")].rstrip("/")
    return urlunparse((p.scheme, p.netloc, path or "", "", "", "")).rstrip("/")


def claude_api_key() -> str | None:
    load_dotenv_from_project()
    raw = os.getenv("CLAUDE_API_KEY")
    return raw.strip() if raw else None


def claude_messages_url() -> str:
    load_dotenv_from_project()
    return os.getenv("CLAUDE_API_URL", _DEFAULT_MESSAGES_URL).strip()


def default_request_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
