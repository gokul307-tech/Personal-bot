from typing import Any

from openai import OpenAI

from app.config.settings import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
)


client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)


def ask_llm(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
):

    kwargs: dict[str, Any] = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
    }

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    response = client.chat.completions.create(
        **kwargs
    )

    return response.choices[0].message