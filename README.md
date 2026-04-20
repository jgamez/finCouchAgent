# FinCoach — Financial Education Teacher Agent

**FinCoach** is a demo platform for a personalized **agentic teacher**: students enter a profile and topic, and **Claude** generates a structured financial-education lesson (text, videos, games, reflections, assessment). The same product idea is implemented **twice** so you can compare architectures:

| Directory | Stack | Port (default) |
|-----------|--------|----------------|
| **`project-1-vanilla`** | Anthropic Python SDK, **manual** tool-use loop | `8000` |
| **`project-2-orchestrated`** | **LangGraph** orchestration + Anthropic API for generation | `8001` |

Both apps call the same **MCP (Model Context Protocol) server** for **structured content and tools** (articles, videos, games, JumpStart-style metadata). The **LLM** still uses the **Anthropic Messages API**; MCP is not a replacement for that API—it supplies tools and data Claude (or the graph) can use.

Open the repo in Cursor/VS Code via **`fincoach.code-workspace`**: three workspace roots (**project 1 vanilla**, **project 2 Orchestrated**, **MCP Server (shared)**)—no duplicate tree—plus shared launch configs.

## Repository layout

```
AIAgents/
├── fincoach.code-workspace          # Multi-root workspace + debug launch configs
├── shared/mcp-servers/content-repository/
│   ├── server.py                    # MCP server (stdio)
│   ├── data/                        # JSON content libraries
│   └── README.md
├── project-1-vanilla/               # Anthropic SDK, manual tool loop
│   ├── agent/
│   │   ├── teacher_agent.py         # Manual agentic loop (tool_use ↔ tool_result)
│   │   ├── mcp_client.py            # MCP stdio client
│   │   ├── anthropic_env.py         # .env loading, API base URL helpers
│   │   └── prompts.py
│   ├── web/                         # FastAPI + Jinja2 + static JS
│   ├── tests/test_claude_api.py     # Optional API connectivity tests (pytest)
│   └── README.md
└── project-2-orchestrated/          # LangGraph orchestration
    ├── agent/
    │   ├── graph.py                 # Compiled lesson + assessment graphs
    │   ├── nodes.py                 # fetch (MCP) → build (Claude) → errors / grade
    │   ├── state.py
    │   ├── mcp_client.py
    │   └── prompts.py
    ├── web/
    └── README.md
```

## Prerequisites

- **Python 3.10+** (the `mcp` package requires 3.10; 3.12 works well).
- **Anthropic API key** from [console.anthropic.com](https://console.anthropic.com/settings/keys) (`sk-ant-…`).
- Optional: **LangSmith** (`LANGCHAIN_API_KEY`, tracing env vars) for **project-2-orchestrated**.

Use a **virtualenv per app** (and one for the MCP server if you run or test it standalone)—see each project README.

## Quick start — `project-1-vanilla`

```bash
cd project-1-vanilla
python3.12 -m venv .venv && source .venv/bin/activate   # or your 3.10+ Python
pip install -r requirements.txt
pip install -r ../shared/mcp-servers/content-repository/requirements.txt

cp .env.example .env
# Set CLAUDE_API_KEY=sk-ant-... (optional: CLAUDE_API_URL)

uvicorn web.app:app --reload --port 8000
# http://localhost:8000
```

## Quick start — `project-2-orchestrated`

```bash
cd project-2-orchestrated
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r ../shared/mcp-servers/content-repository/requirements.txt

cp .env.example .env
# Set ANTHROPIC_API_KEY; optional LangSmith vars for tracing

uvicorn web.app:app --reload --port 8001
# http://localhost:8001
```

## Student flow (both projects)

1. Student submits **name, age, education level, proficiency, topic**.
2. Backend generates a **lesson JSON** (on the order of 8–16 steps).
3. UI walks through steps: content, embedded media, games, reflections, assessment.
4. **Claude** grades the assessment and returns structured feedback.

## Agent architecture (comparison)

**`project-1-vanilla` — Claude drives tools**

Claude receives MCP tools in the Messages API; it issues `tool_use` blocks, the app runs tools against the MCP server, returns `tool_result`, and repeats until the model returns final lesson JSON.

**`project-2-orchestrated` — Graph drives fetch, Claude synthesizes**

LangGraph runs a **`fetch_content`** node that calls the MCP client directly (parallel fetches), then **`build_lesson`** calls Claude once with all context in the prompt (no tool loop in that node). **`handle_error`** can fall back to a simpler Claude-only lesson. Assessment uses a **separate** small graph.

## MCP server

Both projects spawn `shared/mcp-servers/content-repository/server.py` as a **stdio** subprocess (see each project’s `mcp_client.py`). Tools include search, videos, games, and JumpStart-oriented fetch—backed by JSON under `data/` today, replaceable with RAG later.

Details: `shared/mcp-servers/content-repository/README.md`.

## Optional: API smoke test (`project-1-vanilla`)

```bash
cd project-1-vanilla
pytest tests/test_claude_api.py -v
```

Skips if `CLAUDE_API_KEY` is missing or still a placeholder. Requires network access to Anthropic.

## Future enhancements

- [ ] RAG over proprietary content (new MCP tool + vector store)
- [ ] Richer JumpStart / real scraping
- [ ] Embeddable games and real video sources
- [ ] Accounts, history, progress, teacher dashboard, localization
