import json
from typing import Any

from sqlalchemy.orm import Session

from app.agent.executor import ToolExecutor
from app.agent.planner import AgentPlanner
from app.agent.registry import ToolRegistry
from app.llm.client import ask_llm
from app.memory.memory_manager import MemoryManager
from app.prompts.system_prompt import SYSTEM_PROMPT


class VDSSAgent:

    def __init__(
        self,
        registry: ToolRegistry,
        memory_manager: MemoryManager | None = None,
        max_tool_iterations: int = 8,
    ):
        self.registry = registry
        self.executor = ToolExecutor(registry)
        self.memory = memory_manager or MemoryManager()
        self.planner = AgentPlanner()
        self.max_tool_iterations = max(1, int(max_tool_iterations))

    def run(
        self,
        user_message: str,
        db: Session | None = None,
    ) -> str:

        self.memory.add_message(role="user", content=user_message)

        if not self._llm_available():
            return self._run_without_llm(user_message, db)

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self.memory.get_conversation())

        for _ in range(self.max_tool_iterations):
            try:
                response = ask_llm(messages=messages, tools=self.registry.openai_tools())
            except Exception:
                return self._run_without_llm(user_message, db)

            if response is None:
                return self._run_without_llm(user_message, db)

            assistant_content = getattr(response, "content", "") or ""
            tool_calls = getattr(response, "tool_calls", None) or []

            if not tool_calls:
                self.memory.add_message(role="assistant", content=assistant_content)
                return assistant_content.strip() or self._default_direct_answer(user_message)

            assistant_message = {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [],
            }

            for tool_call in tool_calls:
                function = getattr(tool_call, "function", None)
                if function is None:
                    continue
                assistant_message["tool_calls"].append({
                    "id": getattr(tool_call, "id", "call"),
                    "type": "function",
                    "function": {
                        "name": getattr(function, "name", ""),
                        "arguments": getattr(function, "arguments", "{}"),
                    },
                })

            messages.append(assistant_message)

            for tool_call in tool_calls:
                tool_name = getattr(getattr(tool_call, "function", None), "name", "")
                arguments = getattr(getattr(tool_call, "function", None), "arguments", "{}")
                if not tool_name:
                    continue

                if db is not None:
                    arguments = self._inject_database(tool_name, arguments, db)

                result = self.executor.execute(tool_name, arguments)
                try:
                    result_content = json.dumps(result, ensure_ascii=False, default=str)
                except TypeError:
                    result_content = str(result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": getattr(tool_call, "id", "call"),
                    "content": result_content,
                })

        return "I could not complete the requested task within the allowed tool steps."

    @staticmethod
    def _llm_available() -> bool:
        from app.config.settings import OPENROUTER_API_KEY, OPENROUTER_MODEL
        return bool(OPENROUTER_API_KEY and OPENROUTER_MODEL)

    def _run_without_llm(self, user_message: str, db: Session | None) -> str:
        tool_name = self.planner.infer_tool(user_message)

        if tool_name:
            arguments = self.planner.build_tool_arguments(user_message, tool_name)
            if db is not None:
                arguments = self._inject_database(tool_name, arguments, db)
            result = self.executor.execute(tool_name, arguments)
            if isinstance(result, dict) and result.get("success") is False:
                return self._format_tool_failure(tool_name, result)
            return self._format_tool_result(tool_name, result)

        return self._default_direct_answer(user_message)

    @staticmethod
    def _inject_database(
        tool_name: str,
        arguments: str | dict,
        db: Session,
    ) -> dict:

        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                parsed = {}
        elif isinstance(arguments, dict):
            parsed = dict(arguments)
        else:
            parsed = {}

        database_tools = {
            "add_note", "list_notes", "add_mark", "list_marks", "create_plan",
            "list_plans", "remember_information", "recall_information",
            "create_reminder_tool", "list_reminders", "create_event", "list_events",
        }

        if tool_name in database_tools:
            parsed["db"] = db

        return parsed

    @staticmethod
    def _default_direct_answer(user_message: str) -> str:
        text = user_message.lower()

        if "binary search" in text:
            return (
                "Binary search is a fast way to find a value in a sorted list. "
                "It compares the target to the middle element, then keeps searching only on "
                "the half that could still contain it. That reduces the search space dramatically."
            )

        if "recursion" in text:
            return (
                "Recursion is when a function calls itself to solve a smaller version of the same problem. "
                "It is useful for tasks like tree traversal or factorials, but it needs a base case to stop."
            )

        return (
            "I can help with study explanations, calculations, notes, marks, study planning, and revision questions. "
            "If you want, give me a more specific topic or task."
        )

    @staticmethod
    def _format_tool_result(tool_name: str, result: Any) -> str:
        if isinstance(result, dict):
            if tool_name == "calculator":
                return f"The calculation result is {result}."
            if tool_name == "get_datetime":
                return str(result)
            if tool_name == "list_marks":
                marks = result or []
                if not marks:
                    return "I do not see any stored marks for this student yet."
                return "Your saved marks are: " + "; ".join(
                    f"{item.get('subject', 'Subject')}: {item.get('percentage', 0)}%" for item in marks
                )
            if tool_name == "recall_information":
                memories = result or []
                if not memories:
                    return "I do not have a relevant saved memory for this yet."
                return "I remember: " + "; ".join(item.get("content", "") for item in memories[:3])
            if tool_name == "search_knowledge":
                chunks = result or []
                if not chunks:
                    return "I could not find relevant information in the indexed documents for that question."
                return "Relevant material from your documents: " + "; ".join(chunk.get("text", "")[:180] for chunk in chunks[:2])
            if tool_name == "generate_quiz":
                return str(result)
            if tool_name == "create_plan":
                return f"I created a study plan for {result.get('subject') or 'your topic'}: {result.get('title', 'Study plan')}."
            if tool_name == "add_note":
                return f"Your note titled '{result.get('title', 'Untitled')}' has been saved."
            if tool_name == "remember_information":
                return "I have stored that study detail for future help."
            return str(result)

        if isinstance(result, list):
            if not result:
                return "There are no matching results right now."
            return str(result[:3])

        return str(result)

    @staticmethod
    def _format_tool_failure(tool_name: str, result: dict) -> str:
        error = result.get("error") or "The tool did not complete successfully."
        if tool_name == "calculator":
            return f"I could not calculate that safely: {error}"
        return f"I could not complete that step safely: {error}"

