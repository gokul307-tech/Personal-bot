class AgentPlanner:

    """
    Lightweight planner.

    The LLM itself determines which tool is needed.
    This class provides the high-level planning context.
    """

    def build_context(
        self,
        user_message: str,
    ) -> str:

        return (
            "Determine the best way to answer the user's "
            "request. Use an available tool when it provides "
            "more accurate information than reasoning alone.\n\n"
            f"User request:\n{user_message}"
        )