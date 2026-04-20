"""Shared filesystem paths for lesson-format specs (PDFs). Not MCP protocol."""

from pathlib import Path


def monorepo_root() -> Path:
    """project-1-vanilla/agent/lesson_flows/paths.py -> .../AIAgents."""
    return Path(__file__).resolve().parent.parent.parent.parent


def lesson_format_dir() -> Path:
    """Directory for lesson-flow template PDFs (vanilla + orchestrated)."""
    return (
        monorepo_root()
        / "shared"
        / "mcp-servers"
        / "content-repository"
        / "LessonFormat"
    )


def moneylingo_v1_pdf_path() -> Path:
    return lesson_format_dir() / "MoneyLingoLessonTemplate-v1.pdf"
