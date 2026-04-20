# `project-2-orchestrated` — FinCoach (LangGraph)

Financial-education **teacher agent** orchestrated with **LangGraph**: explicit **nodes**, **edges**, and **typed state** instead of a hand-rolled tool loop inside one class.

Claude is still reached through the **Anthropic API** (`AsyncAnthropic` in `nodes.py`). **LangGraph** controls *when* fetching and generation run; **MCP** is used inside the graph’s **`fetch_content`** node, not as a replacement for the LLM API.

## Role in the monorepo

- Same **FinCoach** experience as **`project-1-vanilla`** (FastAPI + Jinja templates, default port **8001**).
- **Contrast**: **`project-1-vanilla`** lets **Claude decide** tool calls via the SDK tool loop; this app **deterministically** fetches from MCP first, then asks Claude to **synthesize** lesson JSON from that bundle (with an error-recovery path).

## Layout

```
project-2-orchestrated/
├── agent/
│   ├── graph.py        # build_lesson_graph(), assessment_graph; compiled singletons
│   ├── nodes.py        # fetch_content (MCP), build_lesson, handle_error, grade_assessment
│   ├── state.py        # TeacherAgentState TypedDict
│   ├── mcp_client.py   # Same stdio MCP pattern as project-1-vanilla
│   └── prompts.py
└── web/
    ├── app.py          # FastAPI; invokes lesson_graph / assessment_graph
    └── templates/
```

## Graph topology (lessons)

```
START → fetch_content → build_lesson ──(ok)──→ END
                           │
                           └──(error)──→ handle_error → END
```

- **`fetch_content`**: parallel MCP calls (`asyncio.gather`) for articles, videos, games, JumpStart helper payload.
- **`build_lesson`**: single `messages.create` with all fetched context in the user message (no tool loop in this node).
- **`handle_error`**: fallback generation if parsing / build fails.

**Assessment** is a **separate** compiled graph: `START → grade_assessment → END`.

## MCP vs `project-1-vanilla`

| | `project-1-vanilla` | `project-2-orchestrated` |
|---|-----------|-----------|
| Who invokes MCP? | Claude via `tool_use` | Graph node `fetch_content` |
| When? | Iterative, model-driven | Once per lesson, upfront (parallel) |
| Good for | Maximum model autonomy | Predictable fetch budget, LangSmith visibility per node |

## Configuration

From `.env.example`:

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Required for `AsyncAnthropic` in `agent/nodes.py`. |
| `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` | Optional LangSmith tracing. |

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY; optional LangSmith keys
```

## Setup

```bash
cd project-2-orchestrated
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt
pip install -r ../shared/mcp-servers/content-repository/requirements.txt

uvicorn web.app:app --reload --port 8001
# http://localhost:8001
```

## Debugging & observability

- **LangSmith**: enable tracing env vars; inspect node inputs/outputs per run.
- **API**: `GET /api/graph-trace/{session_id}` returns a stored trace summary (see `web/app.py`).

## Extending the graph

1. Add an `async def my_node(state: TeacherAgentState) -> dict` in `nodes.py`.
2. `graph.add_node("my_node", my_node)` and wire `add_edge` / `add_conditional_edges` in `graph.py`.

The web layer can keep calling `lesson_graph.ainvoke(...)` with the same state shape as long as `TeacherAgentState` is updated consistently.

## RAG / future content

Same pattern as **`project-1-vanilla`**: add MCP tools in `shared/mcp-servers/content-repository/server.py` and call them from `fetch_content_node` (or add new nodes) so fetched context can come from a vector store instead of static JSON.
