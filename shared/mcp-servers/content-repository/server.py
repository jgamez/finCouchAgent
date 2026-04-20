"""
Content Repository MCP Server
Exposes financial education content, videos, and games as MCP tools.
Both projects consume this server as a subprocess via stdio transport.
"""

import json
import asyncio
import httpx
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    ListToolsResult,
)

DATA_DIR = Path(__file__).parent / "data"

app = Server("content-repository")


def load_json(filename: str) -> list:
    path = DATA_DIR / filename
    if path.exists():
        return json.loads(path.read_text())
    return []


def _topic_phrase(s: str) -> str:
    return " ".join(s.strip().lower().replace("&", " ").split())


def topic_relates(query: str, item_topics: list) -> bool:
    """True if the search topic matches any catalog topic tag (phrase, substring, or word overlap)."""
    if not query or not str(query).strip():
        return True
    q = _topic_phrase(query)
    if not q:
        return True
    tags = [_topic_phrase(t) for t in (item_topics or []) if t]
    if not tags:
        return False
    q_tokens = set(q.split())
    for t in tags:
        if q == t or q in t or t in q:
            return True
        t_tokens = set(t.split())
        if q_tokens & t_tokens:
            return True
    return False


def matches(item: dict, topic: str, audience_level: str, proficiency: str) -> bool:
    """Check if a content item matches the given filters."""
    topic_match = topic_relates(topic, item.get("topics", []))
    level_match = (
        not audience_level
        or audience_level.lower() in [l.lower() for l in item.get("audience_levels", [])]
    )
    prof_match = (
        not proficiency
        or proficiency.lower() in [p.lower() for p in item.get("proficiency_levels", [])]
    )
    return topic_match and level_match and prof_match


@app.list_tools()
async def list_tools() -> ListToolsResult:
    return ListToolsResult(
        tools=[
            Tool(
                name="search_educational_content",
                description=(
                    "Search the financial education content library for textual lessons "
                    "and articles. Returns relevant content chunks for a given topic, "
                    "audience level (middle_school, high_school, college), and proficiency "
                    "(beginner, intermediate, advanced)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Financial topic (e.g. 'budgeting', 'investing', 'credit')",
                        },
                        "audience_level": {
                            "type": "string",
                            "enum": ["middle_school", "high_school", "college"],
                            "description": "Target education level",
                        },
                        "proficiency": {
                            "type": "string",
                            "enum": ["beginner", "intermediate", "advanced"],
                            "description": "Student's financial knowledge level",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default 5)",
                            "default": 5,
                        },
                    },
                    "required": ["topic"],
                },
            ),
            Tool(
                name="get_videos",
                description=(
                    "Retrieve educational videos from the video library tagged by financial "
                    "topic, audience level, and proficiency. Returns video metadata including "
                    "title, URL, duration, and description."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Financial topic to search videos for",
                        },
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
                            "default": 3,
                        },
                    },
                    "required": ["topic"],
                },
            ),
            Tool(
                name="get_games",
                description=(
                    "List standalone HTML/JS mini-games for the FinCoach lesson player. Each result "
                    "includes id, title, description, learning_objectives, topics, audience_levels, "
                    "proficiency_levels, estimated_minutes, and embed_path. "
                    "embed_path is a same-origin URL path (e.g. /static/games/budget-blaster/index.html) "
                    "to use as the iframe src in a game step. Call with a higher max_results (e.g. 8–12) "
                    "when you want several options to choose from for the student's topic and level."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Financial topic the game should reinforce",
                        },
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
                            "description": "How many games to return (default 8; use more for variety)",
                            "default": 8,
                        },
                    },
                    "required": ["topic"],
                },
            ),
            Tool(
                name="fetch_jumpstart_topic",
                description=(
                    "Fetch financial education content from JumpStart.org for a given topic. "
                    "Returns structured content suitable for lesson planning including key "
                    "concepts, definitions, and learning standards."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Financial topic to fetch from JumpStart.org",
                        },
                    },
                    "required": ["topic"],
                },
            ),
        ]
    )


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    if name == "search_educational_content":
        return await _search_educational_content(arguments)
    elif name == "get_videos":
        return await _get_videos(arguments)
    elif name == "get_games":
        return await _get_games(arguments)
    elif name == "fetch_jumpstart_topic":
        return await _fetch_jumpstart_topic(arguments)
    else:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {name}")]
        )


async def _search_educational_content(args: dict) -> CallToolResult:
    topic = args.get("topic", "")
    audience_level = args.get("audience_level", "")
    proficiency = args.get("proficiency", "")
    max_results = args.get("max_results", 5)

    content_items = load_json("content.json")
    results = [
        item for item in content_items
        if matches(item, topic, audience_level, proficiency)
    ][:max_results]

    if not results:
        # Return generic placeholder content if no specific match
        results = [{
            "title": f"Introduction to {topic.title()}",
            "content": (
                f"This lesson covers key concepts in {topic} for {audience_level} students "
                f"at the {proficiency} level. Content will be enhanced with Goalsetter RAG data."
            ),
            "source": "placeholder",
            "topics": [topic],
            "audience_levels": [audience_level],
            "proficiency_levels": [proficiency],
        }]

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(results, indent=2))]
    )


async def _get_videos(args: dict) -> CallToolResult:
    topic = args.get("topic", "")
    audience_level = args.get("audience_level", "")
    proficiency = args.get("proficiency", "")
    max_results = args.get("max_results", 3)

    videos = load_json("videos.json")
    results = [
        v for v in videos
        if matches(v, topic, audience_level, proficiency)
    ][:max_results]

    if not results and topic and videos:
        # Relax proficiency only (topic + audience still required)
        results = [
            v for v in videos
            if topic_relates(topic, v.get("topics", []))
            and (
                not audience_level
                or audience_level.lower()
                in [l.lower() for l in v.get("audience_levels", [])]
            )
        ][:max_results]

    if not results and videos:
        # Last resort: topic-only match, then any videos
        results = [
            v for v in videos if topic_relates(topic, v.get("topics", []))
        ][:max_results]
    if not results and videos:
        results = videos[:max_results]

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(results, indent=2))]
    )


async def _get_games(args: dict) -> CallToolResult:
    topic = args.get("topic", "")
    audience_level = args.get("audience_level", "")
    proficiency = args.get("proficiency", "")
    max_results = args.get("max_results", 8)

    games = load_json("games.json")
    results = [
        g for g in games
        if matches(g, topic, audience_level, proficiency)
    ][:max_results]

    if not results and topic and games:
        results = [
            g for g in games
            if topic_relates(topic, g.get("topics", []))
            and (
                not audience_level
                or audience_level.lower()
                in [l.lower() for l in g.get("audience_levels", [])]
            )
        ][:max_results]

    if not results and games:
        results = [
            g for g in games if topic_relates(topic, g.get("topics", []))
        ][:max_results]
    if not results and games:
        results = games[:max_results]

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(results, indent=2))]
    )


async def _fetch_jumpstart_topic(args: dict) -> CallToolResult:
    topic = args.get("topic", "")

    # In production: scrape or call JumpStart.org API
    # For now: return structured placeholder content with key concepts
    jumpstart_content = {
        "source": "jumpstart.org",
        "topic": topic,
        "standards": [
            f"JA-FIN-{topic[:3].upper()}-1: Understand core concepts of {topic}",
            f"JA-FIN-{topic[:3].upper()}-2: Apply {topic} principles to real-world scenarios",
        ],
        "key_concepts": [
            f"Definition and importance of {topic}",
            f"How {topic} affects personal financial decisions",
            f"Strategies for applying {topic} in everyday life",
            f"Common mistakes related to {topic} and how to avoid them",
        ],
        "vocabulary": [
            {"term": topic.title(), "definition": f"Core concept related to {topic} in personal finance"},
            {"term": "Budget", "definition": "A plan for managing income and expenses"},
            {"term": "Financial Goal", "definition": "A specific financial objective with a target date and amount"},
        ],
        "learning_objectives": [
            f"Students will be able to define {topic} and explain its role in personal finance",
            f"Students will identify at least three strategies for {topic}",
            f"Students will create a personal plan incorporating {topic} principles",
        ],
        "note": (
            "Live JumpStart.org fetching will be integrated via web scraping or API. "
            "Replace this with real content by implementing the HTTP fetch in production."
        ),
    }

    # Attempt actual fetch (gracefully degrades)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            search_url = f"https://www.jumpstart.org/what-we-do/support-financial-education/standards/"
            resp = await client.get(search_url, follow_redirects=True)
            if resp.status_code == 200:
                jumpstart_content["raw_excerpt"] = resp.text[:2000]
    except Exception:
        jumpstart_content["fetch_status"] = "offline_mode"

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(jumpstart_content, indent=2))]
    )


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
