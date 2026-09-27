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

    def plan(self, user_message: str) -> dict:
        """Return a small deterministic plan used to guide the agent."""
        tool = self.infer_tool(user_message)
        text = user_message.lower()
        intent = "conversation"

        if tool == "search_knowledge":
            intent = "document_question"
        elif tool in {"list_marks", "list_plans", "recall_information"}:
            intent = "student_context"
        elif tool:
            intent = tool
        elif any(word in text for word in ("explain", "what is", "how does", "define", "mark answer", "marks answer")):
            intent = "study_question"

        exam_mode = None
        for marks in ("2", "5", "10", "16"):
            if f"{marks} mark" in text or f"{marks}-mark" in text:
                exam_mode = f"{marks}-mark"
                break
        if exam_mode:
            intent = "study_question"

        tasks = []
        if tool:
            tasks.append({"tool": tool, "purpose": "complete the requested study task"})

        return {
            "intent": intent,
            "requires_tools": tool is not None,
            "exam_mode": exam_mode,
            "tasks": tasks,
        }

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
            "weakest subject", "what have i remembered", "my memory",
            "study preferences", "what do you remember"
        ]):
            return "recall_information"

        if any(keyword in text for keyword in [
            "latest", "search the web", "search online", "current release",
        ]):
            return "web_search"

        if any(keyword in text for keyword in [
            "python error", "traceback", "debug this code", "analyze this code",
        ]):
            return "analyze_python_code"

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
            percent_match = re.fullmatch(r"(\d+(?:\.\d+)?)%\s+of\s+(.+)", expr, re.IGNORECASE)
            if percent_match:
                expr = f"({percent_match.group(1)} / 100) * ({percent_match.group(2)})"
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

        if tool_name == "web_search":
            return {"query": text.strip("? ."), "max_results": 5}

        if tool_name == "analyze_python_code":
            return {"code": text}

        return {}