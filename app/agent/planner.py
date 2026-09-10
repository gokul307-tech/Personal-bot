import re


class AgentPlanner:
    """Lightweight planner for intent detection and safe tool selection."""

    def build_context(
        self,
        user_message: str,
    ) -> str:

        return (
            "Answer the student request clearly and efficiently. "
            "Use a tool only when it improves factual accuracy or "
            "relevant student context. Avoid unnecessary tool calls.\n\n"
            f"User request:\n{user_message}"
        )

    def infer_tool(self, user_message: str) -> str | None:
        text = user_message.lower().strip()
        if not text:
            return None

        if any(keyword in text for keyword in [
            "today", "date", "day is it", "what day", "time now", "current time"
        ]):
            return "get_datetime"

        if any(keyword in text for keyword in [
            "calculate", "what is", "compute", "multiply", "plus", "minus", "divide",
            "sum", "difference", "product", "sqrt", "sin", "cos", "tan", "log"
        ]) and re.search(r"\d", text):
            return "calculator"

        if any(keyword in text for keyword in [
            "remember that", "remember ", "save this", "keep in mind", "note that"
        ]):
            return "remember_information"

        if any(keyword in text for keyword in [
            "what do i struggle with", "what topic do i struggle", "weak subject",
            "weakest subject", "what have i remembered", "my memory"
        ]):
            return "recall_information"

        if any(keyword in text for keyword in [
            "save this as a note", "add note", "write a note", "create note", "note:"
        ]):
            return "add_note"

        if any(keyword in text for keyword in [
            "my marks", "marks", "grade", "grades", "score", "scores"
        ]):
            return "list_marks"

        if any(keyword in text for keyword in [
            "study plan", "make a plan", "create a study plan", "schedule my study"
        ]):
            return "create_plan"

        if any(keyword in text for keyword in [
            "quiz", "test me", "generate a quiz", "questions on"
        ]):
            return "generate_quiz"

        if any(keyword in text for keyword in [
            "document", "uploaded", "notes", "pdf", "from my file", "from my document"
        ]):
            return "search_knowledge"

        return None

    def build_tool_arguments(self, user_message: str, tool_name: str) -> dict:
        text = user_message.strip()

        if tool_name == "get_datetime":
            return {"timezone": "Asia/Kolkata"}

        if tool_name == "calculator":
            expr = text
            for prefix in ["calculate", "what is", "compute"]:
                if prefix in text.lower():
                    expr = text[len(prefix):].strip()
                    break
            expr = expr.strip("? .")
            expr = expr.replace("×", "*").replace("÷", "/").replace("^", "**")
            return {"expression": expr}

        if tool_name == "remember_information":
            content = text
            for prefix in ["remember that", "remember ", "keep in mind", "note that"]:
                if content.lower().startswith(prefix):
                    content = content[len(prefix):].strip()
                    break
            return {"content": content.strip("? ."), "memory_type": "study", "importance": 1.0}

        if tool_name == "recall_information":
            return {"memory_type": "study"}

        if tool_name == "add_note":
            title = "Quick note"
            if "note" in text.lower():
                title = text[:60].strip("? .") or title
            return {"title": title, "content": text, "subject": "General"}

        if tool_name == "list_marks":
            return {}

        if tool_name == "create_plan":
            title = "Study plan"
            subject = "General"
            lower = text.lower()
            if "for " in lower:
                subject = text.split("for", 1)[1].strip(" ?.") or subject
            return {"title": title, "subject": subject, "description": text}

        if tool_name == "generate_quiz":
            topic = re.sub(r"^(generate a quiz|quiz|test me)( on| for)?\s*", "", text, flags=re.IGNORECASE).strip("? .") or "General study"
            return {"topic": topic, "number_of_questions": 5, "difficulty": "medium"}

        if tool_name == "search_knowledge":
            query = text.strip("? .")
            return {"query": query, "top_k": 5}

        return {}