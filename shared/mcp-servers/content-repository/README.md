# Content repository MCP server

**FinCoach** uses this server as the **tooling and content layer** for both teacher-agent apps (`project-1-vanilla` and `project-2-orchestrated`). It implements the [Model Context Protocol](https://modelcontextprotocol.io/) over **stdio**: the Python apps spawn `server.py` as a subprocess and exchange JSON-RPC on stdin/stdout.

It does **not** host the LLM. **Claude** is called from each project via the **Anthropic API**. This server exposes **MCP tools** that return structured data (articles, videos, games, standards-style metadata) so the model or the LangGraph nodes can ground lessons in a shared catalog.

## Tools (high level)

| Tool | Role |
|------|------|
| `search_educational_content` | Text / article-style entries from the local JSON library |
| `get_videos` | Video entries filtered by topic, audience, proficiency |
| `get_games` | Game entries filtered similarly |
| `fetch_jumpstart_topic` | JumpStart-oriented payload (placeholder / structured stub; extend as needed) |

Schemas and descriptions are defined in `server.py` (`@app.list_tools()` / `call_tool`).

## Data

JSON files under `data/` (`content.json`, `videos.json`, `games.json`, etc.) back the tools today. Replace or augment with API calls, databases, or RAG by changing the tool handlers only; callers keep using MCP.

## Run / debug standalone

Usually you **do not** run this alone for FinCoach: each app’s `mcp_client.py` starts it automatically.

For MCP Inspector or manual testing:

```bash
cd shared/mcp-servers/content-repository
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

(Expect stdio protocol on the terminal—use an MCP-aware client.)

The **`fincoach.code-workspace`** launch config **“Run MCP Server (direct test)”** debugs `server.py` with the content-repo venv.

## Dependencies

See `requirements.txt` (`mcp`, `httpx`, etc.). Python **3.10+** required.

## Extending

1. Add a `Tool` in `list_tools()` with `inputSchema`.
2. Handle the name in the `call_tool` branch.
3. In **`project-1-vanilla`**, add a `ContentRepositoryClient` method and wire it in `as_anthropic_tools()`.
4. In **`project-2-orchestrated`**, call the new client method from `fetch_content_node` (or a new graph node).
