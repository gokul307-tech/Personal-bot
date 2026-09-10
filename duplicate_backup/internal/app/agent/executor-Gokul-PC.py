import json
from typing import Any

from app.agent.registry import ToolRegistry


class ToolExecutor:

    def __init__(
        self,
        registry: ToolRegistry,
    ):
        self.registry = registry

    def execute(
        self,
        name: str,
        arguments: str | dict[str, Any],
    ) -> Any:

        tool = self.registry.get(name)

        if tool is None:
            return {
                "success": False,
                "error": f"Unknown tool: {name}",
            }

        if isinstance(arguments, str):

            try:
                arguments = json.loads(arguments)

            except json.JSONDecodeError as exc:

                return {
                    "success": False,
                    "error": (
                        f"Invalid tool arguments: {exc}"
                    ),
                }

        if not isinstance(arguments, dict):

            return {
                "success": False,
                "error": "Tool arguments must be an object.",
            }

        try:

            return tool["function"](**arguments)

        except Exception as exc:

            return {
                "success": False,
                "error": (
                    f"Tool '{name}' failed: {exc}"
                ),
            }