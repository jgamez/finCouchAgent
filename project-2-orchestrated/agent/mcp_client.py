"""
MCP Client for Project 2.
Identical transport pattern to Project 1 — stdio to the shared content-repository server.
In the LangGraph version, the MCP client is called directly inside the fetch_content_node
rather than being handed to Claude as tools. This demonstrates a different integration pattern:
  - Project 1: Claude decides WHEN to call tools (agentic tool-use loop)
  - Project 2: LangGraph decides WHEN to fetch (deterministic fetch node),
               Claude only synthesizes (no tool calls needed in build_lesson_node)
"""

import json
import sys
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


MCP_SERVER_PATH = (
    Path(__file__).parent.parent.parent
    / "shared"
    / "mcp-servers"
    / "content-repository"
    / "server.py"
)


class ContentRepositoryClient:
    def __init__(self):
        self._session = None
        self._client_cm = None
        self._session_cm = None

    async def connect(self):
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(MCP_SERVER_PATH)],
        )
        self._client_cm = stdio_client(server_params)
        read, write = await self._client_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()

    async def disconnect(self):
        if self._session_cm:
            await self._session_cm.__aexit__(None, None, None)
        if self._client_cm:
            await self._client_cm.__aexit__(None, None, None)

    async def search_educational_content(self, topic, audience_level="", proficiency="", max_results=5):
        return await self._call("search_educational_content", {
            "topic": topic, "audience_level": audience_level,
            "proficiency": proficiency, "max_results": max_results,
        })

    async def get_videos(self, topic, audience_level="", proficiency="", max_results=3):
        return await self._call("get_videos", {
            "topic": topic, "audience_level": audience_level,
            "proficiency": proficiency, "max_results": max_results,
        })

    async def get_games(self, topic, audience_level="", proficiency="", max_results=10):
        return await self._call("get_games", {
            "topic": topic, "audience_level": audience_level,
            "proficiency": proficiency, "max_results": max_results,
        })

    async def fetch_jumpstart_topic(self, topic):
        result = await self._call("fetch_jumpstart_topic", {"topic": topic})
        return result if isinstance(result, dict) else (result[0] if result else {})

    async def _call(self, tool_name: str, args: dict) -> Any:
        result = await self._session.call_tool(tool_name, args)
        if result.content and result.content[0].type == "text":
            try:
                return json.loads(result.content[0].text)
            except json.JSONDecodeError:
                return result.content[0].text
        return None


@asynccontextmanager
async def get_mcp_client():
    client = ContentRepositoryClient()
    await client.connect()
    try:
        yield client
    finally:
        await client.disconnect()
