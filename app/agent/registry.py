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
    from app.tools.calendar import create_event, list_events
    from app.tools.code_analyzer import analyze_python_code
    from app.tools.datetime_tool import get_datetime
    from app.tools.file_reader import read_file
    from app.tools.marks import add_mark, list_marks
    from app.tools.memory import recall_information, remember_information
    from app.tools.notes import add_note, list_notes
    from app.tools.pdf_reader import read_pdf
    from app.tools.python_analysis import analyze_csv
    from app.tools.quiz import generate_quiz
    from app.tools.rag import ingest_project_document, search_knowledge
    from app.tools.reminders import create_reminder_tool, list_reminders
    from app.tools.study_planner import create_plan, list_plans
    from app.tools.web_search import web_search

    registry = ToolRegistry()

    registry.register(
        name="calculator",
        description=(
            "Use for arithmetic and safe mathematical evaluation. "
            "Use this when the user asks for a calculation or numeric result."
        ),
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "A valid arithmetic expression like '1234 * 5678' or 'sqrt(144)'.",
                }
            },
            "required": ["expression"],
        },
        function=calculator,
    )

    registry.register(
        name="get_datetime",
        description=(
            "Use when the user asks for today's date, current time, or a day/time reference."
        ),
        parameters={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone such as Asia/Kolkata.",
                }
            },
        },
        function=get_datetime,
    )

    registry.register(
        name="read_file",
        description="Read a text or code file from disk when the student references a local file.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute or project-relative file path."}
            },
            "required": ["file_path"],
        },
        function=read_file,
    )

    registry.register(
        name="read_pdf",
        description="Extract text from a PDF file for study or document questions.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the PDF file."}
            },
            "required": ["file_path"],
        },
        function=read_pdf,
    )

    registry.register(
        name="add_note",
        description="Create a note for the student in the database.",
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
        description="List saved notes, optionally filtered by subject.",
        parameters={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "user_id": {"type": "integer"},
            },
        },
        function=list_notes,
    )

    registry.register(
        name="add_mark",
        description="Store a subject mark or assignment score.",
        parameters={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "marks_obtained": {"type": "number"},
                "maximum_marks": {"type": "number"},
                "exam_name": {"type": "string"},
                "user_id": {"type": "integer"},
            },
            "required": ["subject", "marks_obtained", "maximum_marks"],
        },
        function=add_mark,
    )

    registry.register(
        name="list_marks",
        description="Retrieve marks for a student to assess performance and weak subjects.",
        parameters={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "user_id": {"type": "integer"},
            },
        },
        function=list_marks,
    )

    registry.register(
        name="create_plan",
        description="Create a study plan or planned learning task for the student.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "scheduled_at": {"type": "string", "description": "ISO datetime string."},
                "user_id": {"type": "integer"},
            },
            "required": ["title"],
        },
        function=create_plan,
    )

    registry.register(
        name="list_plans",
        description="Retrieve existing study plans for the student.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
            },
        },
        function=list_plans,
    )

    registry.register(
        name="generate_quiz",
        description="Generate a targeted quiz for a topic so the student can practice.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "number_of_questions": {"type": "integer", "minimum": 1, "maximum": 20},
                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
            },
            "required": ["topic"],
        },
        function=generate_quiz,
    )

    registry.register(
        name="web_search",
        description="Search the web for up-to-date information when the user needs current facts.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
        function=web_search,
    )

    registry.register(
        name="ingest_project_document",
        description="Index a project document so it can be retrieved later via knowledge search.",
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
        description="Search the indexed project documents for relevant chunks and context.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
        function=search_knowledge,
    )

    registry.register(
        name="analyze_csv",
        description="Analyze a CSV file statistically without executing code.",
        parameters={
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
        function=analyze_csv,
    )

    registry.register(
        name="analyze_python_code",
        description="Analyze Python code for issues without executing it.",
        parameters={
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
        function=analyze_python_code,
    )

    registry.register(
        name="remember_information",
        description="Store useful long-term study information, preferences, or recurring problems.",
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
        description="Retrieve relevant stored memories for the current student context.",
        parameters={
            "type": "object",
            "properties": {
                "memory_type": {"type": "string"},
                "user_id": {"type": "integer"},
            },
        },
        function=recall_information,
    )

    registry.register(
        name="create_reminder_tool",
        description="Create a study reminder for the student.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "remind_at": {"type": "string", "description": "ISO datetime string."},
                "description": {"type": "string"},
                "user_id": {"type": "integer"},
            },
            "required": ["title", "remind_at"],
        },
        function=create_reminder_tool,
    )

    registry.register(
        name="list_reminders",
        description="List upcoming reminders for the student.",
        parameters={
            "type": "object",
            "properties": {"user_id": {"type": "integer"}},
        },
        function=list_reminders,
    )

    registry.register(
        name="create_event",
        description="Create a calendar event for classes, study blocks, or deadlines.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_time": {"type": "string", "description": "ISO datetime string."},
                "end_time": {"type": "string", "description": "ISO datetime string."},
                "description": {"type": "string"},
                "user_id": {"type": "integer"},
            },
            "required": ["title", "start_time"],
        },
        function=create_event,
    )

    registry.register(
        name="list_events",
        description="List calendar events for the student.",
        parameters={
            "type": "object",
            "properties": {"user_id": {"type": "integer"}},
        },
        function=list_events,
    )

    return registry