from typing import Any

from openai import OpenAI

from app.config.settings import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
)
from app.llm.model_config import SUPPORTED_PARAMETERS


client = None
if OPENROUTER_API_KEY:
    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        timeout=60.0,
        max_retries=0,
    )


def ask_llm(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    timeout: float | None = None,
):

    if client is None or not OPENROUTER_API_KEY:
        raise RuntimeError("OpenRouter API key is not configured.")

    kwargs: dict[str, Any] = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        **SUPPORTED_PARAMETERS,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    response = client.chat.completions.create(**kwargs)
    if not response.choices or response.choices[0].message is None:
        raise RuntimeError("OpenRouter returned no assistant response.")
    return response.choices[0].message