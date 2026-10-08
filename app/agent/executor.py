import json
import logging
from typing import Any

from app.agent.registry import ToolRegistry


logger = logging.getLogger(__name__)


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

        if not name or not isinstance(name, str):
            return {
                "success": False,
                "error": "Tool name is required.",
            }

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
                    "error": f"Invalid tool arguments: {exc}",
                }

        if not isinstance(arguments, dict):
            return {
                "success": False,
                "error": "Tool arguments must be an object.",
            }

        required = tool.get("parameters", {}).get("required", [])
        if not isinstance(required, list) or any(not isinstance(field, str) for field in required):
            return {
                "success": False,
                "error": "Tool has an invalid required-argument definition.",
            }
        for field in required:
            if field not in arguments:
                return {
                    "success": False,
                    "error": f"Missing required argument: {field}",
                }
            value = arguments[field]
            if value is None or (isinstance(value, str) and not value.strip()):
                return {
                    "success": False,
                    "error": f"Required argument '{field}' cannot be blank.",
                }

        try:
            return tool["function"](**arguments)
        except TypeError as exc:
            logger.info("Tool '%s' rejected its arguments: %s", name, exc)
            return {
                "success": False,
                "error": f"Invalid arguments for '{name}'.",
            }
        except Exception as exc:
            logger.exception("Tool '%s' raised an unexpected error", name)
            return {
                "success": False,
                "error": f"Tool '{name}' failed unexpectedly.",
            }