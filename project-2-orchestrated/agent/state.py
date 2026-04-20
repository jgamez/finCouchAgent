"""
LangGraph State for the Teacher Agent.

State is the shared data structure that flows through the graph.
Every node reads from state and writes back to it.
"""

from typing import TypedDict, Annotated, Optional, NotRequired
import operator


class StudentProfile(TypedDict):
    name: str
    age: int
    audience_level: str   # middle_school | high_school | college
    proficiency: str      # beginner | intermediate | advanced
    topic: str


class LessonStep(TypedDict):
    step_number: int
    step_type: str        # intro|content|video|game|reflection|quiz|open_question|challenge
    title: str
    content: Optional[str]
    video: Optional[dict]
    game: Optional[dict]
    assessment: Optional[dict]


class Lesson(TypedDict):
    lesson_title: str
    topic: str
    audience_level: str
    proficiency: str
    estimated_minutes: int
    learning_objectives: list[str]
    steps: list[LessonStep]
    completion_message: str


class AssessmentResult(TypedDict):
    score: int
    total_points: int
    percentage: float
    grade: str
    feedback_per_question: list[dict]
    overall_feedback: str
    mastery_level: str
    review_topics: list[str]


class TeacherAgentState(TypedDict):
    """
    The full state of the teacher agent workflow.
    Annotated[list, operator.add] means new items are appended (not replaced).
    """
    # Set by the web app for progressive lesson publishing (not part of graph semantics)
    session_id: NotRequired[Optional[str]]

    # Student profile (set once at start)
    profile: Optional[StudentProfile]

    # Content fetched from MCP tools
    fetched_content: Annotated[list[dict], operator.add]
    fetched_videos: Annotated[list[dict], operator.add]
    fetched_games: Annotated[list[dict], operator.add]
    jumpstart_content: Optional[dict]

    # Outline from pre-fetch Claude call (step titles only); full lesson built after MCP fetch
    lesson_outline: NotRequired[Optional[dict]]

    # Generated lesson
    lesson: Optional[Lesson]
    lesson_error: Optional[str]

    # Assessment
    student_answers: Optional[list[dict]]
    assessment_result: Optional[AssessmentResult]

    # Workflow control
    current_phase: str   # "profile"|"fetching"|"building"|"ready"|"assessing"|"done"
    messages: Annotated[list[dict], operator.add]   # full message history for Claude

    # UI: agentic steps shown on the generating-lesson overlay (append-only)
    generation_log: Annotated[list[dict], operator.add]
