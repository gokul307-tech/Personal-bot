from typing import Any, Callable


class ToolRegistry:

    def __init__(self):
        self._tools: dict[
            str,
            dict[str, Any],
        ] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        function: Callable,
    ) -> None:

        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "function": function,
        }

    def get(
        self,
        name: str,
    ) -> dict[str, Any] | None:

        return self._tools.get(name)

    def openai_tools(self) -> list[dict]:

        return [
            {
                "type": "function",
                "function": {
                    "name": item["name"],
                    "description": item["description"],
                    "parameters": item["parameters"],
                },
            }
            for item in self._tools.values()
        ]

    def names(self) -> list[str]:
        return list(self._tools.keys())


def create_default_registry() -> ToolRegistry:

    from app.tools.calculator import calculator
    from app.tools.datetime_tool import get_datetime
    from app.tools.file_reader import read_file
    from app.tools.pdf_reader import read_pdf

    from app.tools.notes import (
        add_note,
        list_notes,
    )

    from app.tools.marks import (
        add_mark,
        list_marks,
    )

    from app.tools.study_planner import (
        create_plan,
        list_plans,
    )

    from app.tools.quiz import generate_quiz

    from app.tools.web_search import web_search

    from app.tools.rag import (
        ingest_project_document,
        search_knowledge,
    )

    from app.tools.python_analysis import (
        analyze_csv,
    )

    from app.tools.code_analyzer import (
        analyze_python_code,
    )

    from app.tools.memory import (
        remember_information,
        recall_information,
    )

    from app.tools.reminders import (
        create_reminder_tool,
        list_reminders,
    )

    from app.tools.calendar import (
        create_event,
        list_events,
    )

    registry = ToolRegistry()

    # -----------------------------------------------------
    # Calculator
    # -----------------------------------------------------

    registry.register(
        name="calculator",
        description=(
            "Safely calculate mathematical expressions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "Mathematical expression."
                    ),
                }
            },
            "required": ["expression"],
        },
        function=calculator,
    )

    # -----------------------------------------------------
    # Date/time
    # -----------------------------------------------------

    registry.register(
        name="get_datetime",
        description=(
            "Get the current date and time for a timezone."
        ),
        parameters={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": (
                        "IANA timezone such as "
                        "Asia/Kolkata."
                    ),
                }
            },
        },
        function=get_datetime,
    )

    # -----------------------------------------------------
    # File
    # -----------------------------------------------------

    registry.register(
        name="read_file",
        description=(
            "Read a supported text/code file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file.",
                }
            },
            "required": ["file_path"],
        },
        function=read_file,
    )

    # -----------------------------------------------------
    # PDF
    # -----------------------------------------------------

    registry.register(
        name="read_pdf",
        description=(
            "Extract text from a PDF document."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the PDF.",
                }
            },
            "required": ["file_path"],
        },
        function=read_pdf,
    )

    # -----------------------------------------------------
    # Notes
    # -----------------------------------------------------

    registry.register(
        name="add_note",
        description="Create a student note.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "subject": {"type": "string"},
                "user_id": {"type": "integer"},
            },
            "required": ["title", "content"],
        },
        function=add_note,
    )

    registry.register(
        name="list_notes",
        description="Retrieve student notes.",
        parameters={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "user_id": {"type": "integer"},
            },
        },
        function=list_notes,
    )

    # -----------------------------------------------------
    # Marks
    # -----------------------------------------------------

    registry.register(
        name="add_mark",
        description="Store an exam mark.",
        parameters={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "marks_obtained": {"type": "number"},
                "maximum_marks": {"type": "number"},
                "exam_name": {"type": "string"},
                "user_id": {"type": "integer"},
            },
            "required": [
                "subject",
                "marks_obtained",
                "maximum_marks",
            ],
        },
        function=add_mark,
    )

    registry.register(
        name="list_marks",
        description="Retrieve stored exam marks.",
        parameters={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "user_id": {"type": "integer"},
            },
        },
        function=list_marks,
    )

    # -----------------------------------------------------
    # Study planning
    # -----------------------------------------------------

    registry.register(
        name="create_plan",
        description="Create a study plan item.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "scheduled_at": {
                    "type": "string",
                    "description": (
                        "ISO datetime."
                    ),
                },
                "user_id": {"type": "integer"},
            },
            "required": ["title"],
        },
        function=create_plan,
    )

    registry.register(
        name="list_plans",
        description="Retrieve study plans.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
            },
        },
        function=list_plans,
    )

    # -----------------------------------------------------
    # Quiz
    # -----------------------------------------------------

    registry.register(
        name="generate_quiz",
        description=(
            "Generate a multiple-choice educational quiz."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "number_of_questions": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                },
                "difficulty": {
                    "type": "string",
                    "enum": [
                        "easy",
                        "medium",
                        "hard",
                    ],
                },
            },
            "required": ["topic"],
        },
        function=generate_quiz,
    )

    # -----------------------------------------------------
    # Web search
    # -----------------------------------------------------

    registry.register(
        name="web_search",
        description=(
            "Search the web for current information."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        },
        function=web_search,
    )

    # -----------------------------------------------------
    # RAG
    # -----------------------------------------------------

    registry.register(
        name="ingest_project_document",
        description=(
            "Index a document located inside the "
            "project's data/documents directory."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
            },
            "required": ["filename"],
        },
        function=ingest_project_document,
    )

    registry.register(
        name="search_knowledge",
        description=(
            "Search indexed project documents."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        },
        function=search_knowledge,
    )

    # -----------------------------------------------------
    # CSV analysis
    # -----------------------------------------------------

    registry.register(
        name="analyze_csv",
        description=(
            "Analyze a CSV file statistically "
            "without executing code."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
            },
            "required": ["file_path"],
        },
        function=analyze_csv,
    )

    # -----------------------------------------------------
    # Python code analysis
    # -----------------------------------------------------

    registry.register(
        name="analyze_python_code",
        description=(
            "Analyze Python source code without "
            "executing it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string"},
            },
            "required": ["code"],
        },
        function=analyze_python_code,
    )

    # -----------------------------------------------------
    # Memory
    # -----------------------------------------------------

    registry.register(
        name="remember_information",
        description=(
            "Store information for future conversations."
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "memory_type": {"type": "string"},
                "importance": {"type": "number"},
                "user_id": {"type": "integer"},
            },
            "required": ["content"],
        },
        function=remember_information,
    )

    registry.register(
        name="recall_information",
        description=(
            "Retrieve stored memories."
        ),
        parameters={
            "type": "object",
            "properties": {
                "memory_type": {"type": "string"},
                "user_id": {"type": "integer"},
            },
        },
        function=recall_information,
    )

    # -----------------------------------------------------
    # Reminders
    # -----------------------------------------------------

    registry.register(
        name="create_reminder_tool",
        description="Create a study reminder.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "remind_at": {
                    "type": "string",
                    "description": "ISO datetime.",
                },
                "description": {"type": "string"},
                "user_id": {"type": "integer"},
            },
            "required": [
                "title",
                "remind_at",
            ],
        },
        function=create_reminder_tool,
    )

    registry.register(
        name="list_reminders",
        description="List study reminders.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
            },
        },
        function=list_reminders,
    )

    # -----------------------------------------------------
    # Calendar
    # -----------------------------------------------------

    registry.register(
        name="create_event",
        description="Create a calendar event.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_time": {
                    "type": "string",
                    "description": "ISO datetime.",
                },
                "end_time": {
                    "type": "string",
                    "description": "ISO datetime.",
                },
                "description": {"type": "string"},
                "user_id": {"type": "integer"},
            },
            "required": [
                "title",
                "start_time",
            ],
        },
        function=create_event,
    )

    registry.register(
        name="list_events",
        description="List calendar events.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
            },
        },
        function=list_events,
    )

    return registry