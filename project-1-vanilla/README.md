# `project-1-vanilla` — FinCoach (Anthropic SDK)

Financial-education **teacher agent** using the **Anthropic Python SDK** only: a hand-written **agentic loop** (tool calls in, tool results out) with **no** LangGraph/LangChain orchestration.

## Role in the monorepo

- **Same UX goal** as **`project-2-orchestrated`**: profile + topic → lesson JSON → step UI → graded assessment.
- **MCP** supplies tools (content, videos, games, JumpStart helper). **Claude** is invoked via **`AsyncAnthropic`** and the Messages API.
- **`project-2-orchestrated`** implements the same idea with **LangGraph** and a different MCP usage pattern (see its README).

## Architecture

```
project-1-vanilla/
├── agent/
│   ├── teacher_agent.py    # Manual loop: messages.create + tool_use handling
│   ├── mcp_client.py       # MCP stdio client → ../shared/mcp-servers/content-repository
│   ├── anthropic_env.py    # load_dotenv, CLAUDE_API_URL → SDK base URL, headers helper
│   └── prompts.py          # System prompts (audience / proficiency aware)
├── web/
│   ├── app.py              # FastAPI: pages + /api/* on one app, one port
│   ├── templates/          # Jinja2
│   └── static/
└── tests/
    └── test_claude_api.py  # Pytest integration checks (optional)
```

## Agentic loop (high level)

1. Student submits profile + topic (`POST /api/start-lesson`).
2. Background task runs `TeacherAgent.generate_lesson()`.
3. MCP tools are registered as Anthropic tool definitions (`mcp_client.as_anthropic_tools()`).
4. Loop: `messages.create` with tools → if `stop_reason == tool_use`, execute tools via MCP → append `tool_result` → repeat.
5. When Claude finishes, lesson JSON is parsed from the final message.
6. Frontend polls `/api/lesson-status/{id}` then renders `/lesson/{id}`.
7. Assessment: `TeacherAgent.grade_assessment()` with another Messages call.

## MCP transport

- **Stdio**: `ContentRepositoryClient` starts `server.py` with `sys.executable` and talks over stdin/stdout.
- Server path is resolved relative to the repo (`shared/mcp-servers/content-repository/server.py`).

To add tools: extend the MCP server’s tool list and handlers, then add client methods and include them in `as_anthropic_tools()`.

## Configuration

| Variable | Purpose |
|----------|---------|
| `CLAUDE_API_KEY` | Required. Anthropic [API key](https://console.anthropic.com/settings/keys) (`sk-ant-…`). |
| `CLAUDE_API_URL` | Optional. Default `https://api.anthropic.com/v1/messages`; SDK base URL is derived in `anthropic_env.py`. |

Copy `.env.example` → `.env`. The web app loads env via `load_dotenv_from_project()` in `anthropic_env.py` so imports work from different working directories.

## Setup

```bash
cd project-1-vanilla
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt
pip install -r ../shared/mcp-servers/content-repository/requirements.txt

cp .env.example .env
# Edit .env: CLAUDE_API_KEY=sk-ant-...

uvicorn web.app:app --reload --port 8000
# http://localhost:8000
```

## Tests

```bash
pytest tests/test_claude_api.py -v
```

Uses the same env as `.env` (real key required; placeholder values are skipped). Handy for verifying keys and TLS/proxy issues outside the browser.

## Design choices

- **Explicit tool loop**: easy to log and debug each tool round-trip.
- **MCP as subprocess**: swap or upgrade the content server without changing the agent’s transport assumptions.
- **Async end-to-end**: FastAPI + `AsyncAnthropic` + async MCP client for concurrency during generation.
- **Lesson as JSON**: one structured payload drives the whole UI flow.

## RAG / future content

Replace or supplement `data/*.json` in the MCP server with a vector search tool; register it in the MCP server and in `as_anthropic_tools()` so Claude can call it like any other tool.
