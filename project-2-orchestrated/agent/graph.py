"""
LangGraph Graph Definition for the Teacher Agent.

This wires all nodes into a directed graph with conditional routing.

Graph topology:

  [START]
     │
     ▼
  outline_lesson         ← No tools: step titles for sidebar (fast)
     │
     ▼
  fetch_content          ← Calls MCP server (parallel tool calls)
     │
     ▼
  build_lesson           ← Claude synthesizes content into lesson JSON
     │
  ┌──┴──────────────┐
  │ (error?)         │
  ▼                  ▼
handle_error    [ready END]   ← Lesson is ready; web app serves it
  │
  ▼
[ready END]

Assessment flow (triggered separately):
  [ASSESS_START]
     │
     ▼
  grade_assessment
     │
     ▼
  [ASSESS_END]
"""

from langgraph.graph import StateGraph, START, END

from agent.state import TeacherAgentState
from agent.nodes import (
    outline_lesson_node,
    fetch_content_node,
    build_lesson_node,
    grade_assessment_node,
    handle_error_node,
    route_after_build,
)


def build_lesson_graph() -> StateGraph:
    """
    Builds and compiles the lesson generation graph.
    Returns a compiled LangGraph app.
    """
    graph = StateGraph(TeacherAgentState)

    # ── Add nodes ──────────────────────────────────────────────────────────────
    graph.add_node("outline_lesson", outline_lesson_node)
    graph.add_node("fetch_content", fetch_content_node)
    graph.add_node("build_lesson", build_lesson_node)
    graph.add_node("handle_error", handle_error_node)

    # ── Add edges ──────────────────────────────────────────────────────────────
    graph.add_edge(START, "outline_lesson")
    graph.add_edge("outline_lesson", "fetch_content")
    graph.add_edge("fetch_content", "build_lesson")

    # Conditional routing after build: success or error recovery
    graph.add_conditional_edges(
        "build_lesson",
        route_after_build,
        {
            "ready": END,
            "handle_error": "handle_error",
        },
    )

    graph.add_edge("handle_error", END)

    return graph.compile()


def build_assessment_graph() -> StateGraph:
    """
    A separate graph just for grading — keeps concerns separated.
    """
    graph = StateGraph(TeacherAgentState)
    graph.add_node("grade_assessment", grade_assessment_node)
    graph.add_edge(START, "grade_assessment")
    graph.add_edge("grade_assessment", END)
    return graph.compile()


# Module-level singletons (compiled once, reused across requests)
lesson_graph = build_lesson_graph()
assessment_graph = build_assessment_graph()
