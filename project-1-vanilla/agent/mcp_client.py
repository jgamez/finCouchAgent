"""
MCP Client wrapper for connecting to the content-repository MCP server.
Uses stdio transport — launches the MCP server as a subprocess.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# Path to the shared MCP server
MCP_SERVER_PATH = (
    Path(__file__).parent.parent.parent
    / "shared"
    / "mcp-servers"
    / "content-repository"
    / "server.py"
)


class ContentRepositoryClient:
    """
    Wraps the MCP content-repository server.
    Provides async methods for each tool.
    """

    def __init__(self):
        self._session: ClientSession | None = None
        self._client_cm = None
        self._session_cm = None

    async def connect(self):
        """Start the MCP server subprocess and initialize the session."""
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(MCP_SERVER_PATH)],
            env=None,
        )
        self._client_cm = stdio_client(server_params)
        read, write = await self._client_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()

    async def disconnect(self):
        """Clean up the session and subprocess."""
        if self._session_cm:
            await self._session_cm.__aexit__(None, None, None)
        if self._client_cm:
            await self._client_cm.__aexit__(None, None, None)

    async def list_tools(self) -> list[dict]:
        """List all available tools from the MCP server."""
        result = await self._session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in result.tools
        ]

    async def search_educational_content(
        self,
        topic: str,
        audience_level: str = "",
        proficiency: str = "",
        max_results: int = 5,
    ) -> list[dict]:
        result = await self._session.call_tool(
            "search_educational_content",
            {
                "topic": topic,
                "audience_level": audience_level,
                "proficiency": proficiency,
                "max_results": max_results,
            },
        )
        return self._parse_result(result)

    async def get_videos(
        self,
        topic: str,
        audience_level: str = "",
        proficiency: str = "",
        max_results: int = 3,
    ) -> list[dict]:
        result = await self._session.call_tool(
            "get_videos",
            {
                "topic": topic,
                "audience_level": audience_level,
                "proficiency": proficiency,
                "max_results": max_results,
            },
        )
        return self._parse_result(result)

    async def get_games(
        self,
        topic: str,
        audience_level: str = "",
        proficiency: str = "",
        max_results: int = 10,
    ) -> list[dict]:
        result = await self._session.call_tool(
            "get_games",
            {
                "topic": topic,
                "audience_level": audience_level,
                "proficiency": proficiency,
                "max_results": max_results,
            },
        )
        return self._parse_result(result)

    async def fetch_jumpstart_topic(self, topic: str) -> dict:
        result = await self._session.call_tool(
            "fetch_jumpstart_topic",
            {"topic": topic},
        )
        parsed = self._parse_result(result)
        return parsed if isinstance(parsed, dict) else parsed[0] if parsed else {}

    def _parse_result(self, result) -> Any:
        """Parse MCP tool call result into Python objects."""
        if result.content and result.content[0].type == "text":
            try:
                return json.loads(result.content[0].text)
            except json.JSONDecodeError:
                return result.content[0].text
        return None

    def as_anthropic_tools(self) -> list[dict]:
        """
        Returns tool definitions in Anthropic API format.
        Used to pass tools to the Claude API for agentic tool use.
        """
        return [
            {
                "name": "search_educational_content",
                "description": "Search the financial education content library for textual lessons and articles.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "audience_level": {
                            "type": "string",
                            "enum": ["middle_school", "high_school", "college"],
                        },
                        "proficiency": {
                            "type": "string",
                            "enum": ["beginner", "intermediate", "advanced"],
                        },
                        "max_results": {"type": "integer"},
                    },
                    "required": ["topic"],
                },
            },
            {
                "name": "get_videos",
                "description": "Retrieve educational videos tagged by financial topic, audience level, and proficiency.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "audience_level": {
                            "type": "string",
                            "enum": ["middle_school", "high_school", "college"],
                        },
                        "proficiency": {
                            "type": "string",
                            "enum": ["beginner", "intermediate", "advanced"],
                        },
                        "max_results": {"type": "integer"},
                    },
                    "required": ["topic"],
                },
            },
            {
                "name": "get_games",
                "description": (
                    "List HTML/JS mini-games for lessons. Each item includes id, title, description, "
                    "topics, embed_path (iframe URL path like /static/games/slug/index.html), "
                    "and estimated_minutes. Use max_results 8–12 to compare options before picking one."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "audience_level": {
                            "type": "string",
                            "enum": ["middle_school", "high_school", "college"],
                        },
                        "proficiency": {
                            "type": "string",
                            "enum": ["beginner", "intermediate", "advanced"],
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Number of games to return; prefer 8 or more for choice",
                        },
                    },
                    "required": ["topic"],
                },
            },
            {
                "name": "fetch_jumpstart_topic",
                "description": "Fetch financial education content from JumpStart.org for a given topic.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                    },
                    "required": ["topic"],
                },
            },
        ]


@asynccontextmanager
async def get_mcp_client():
    """Context manager for the MCP client lifecycle."""
    client = ContentRepositoryClient()
    await client.connect()
    try:
        yield client
    finally:
        await client.disconnect()
