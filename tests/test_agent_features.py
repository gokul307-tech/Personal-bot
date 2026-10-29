import logging
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

import app.agent.agent as agent_module
from app.agent.agent import VDSSAgent
from app.agent.planner import AgentPlanner
from app.agent.registry import create_default_registry
from app.agent.executor import ToolExecutor
from app.agent.registry import ToolRegistry
from app.llm import client as llm_client
from app.rag import retriever


def test_planner_classifies_exam_and_calculator_intent():
    planner = AgentPlanner()
    plan = planner.plan("Give me a 5 mark answer for Round Robin scheduling.")
    assert plan["intent"] == "study_question"
    assert plan["exam_mode"] == "5-mark"

    arguments = planner.build_tool_arguments("Calculate 25% of 480.", "calculator")
    assert arguments["expression"] == "(25 / 100) * (480)"

    plan = planner.build_tool_arguments(
        "Create a study plan for I have 3 days to prepare for OS. Save it using the study-plan tool.",
        "create_plan",
    )
    assert plan["subject"] == "OS"


def test_planner_fast_path_only_applies_to_direct_questions():
    planner = AgentPlanner()

    assert planner.fast_path("Explain recursion simply.")["requires_tools"] is False
    assert planner.fast_path("Calculate 25 * 4.") is None
    assert planner.fast_path("Give me a 5-mark answer on OS.") is None


def test_simple_llm_request_omits_unneeded_tool_schema(monkeypatch):
    captured = {}

    def fake_llm(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content="A direct answer.", tool_calls=[])

    agent = VDSSAgent(create_default_registry())
    monkeypatch.setattr(agent, "_llm_available", lambda: True)
    monkeypatch.setattr("app.agent.agent.ask_llm", fake_llm)

    assert agent.run("Explain recursion simply.") == "A direct answer."
    assert captured["tools"] is None
    assert captured["timeout"] > 0


def test_agent_enforces_deadline_between_sequential_tool_rounds(monkeypatch, caplog):
    clock = [0.0]
    monkeypatch.setattr(agent_module.time, "monotonic", lambda: clock[0])

    registry = ToolRegistry()

    def run_tool():
        clock[0] = 11.0
        return {"success": True}

    registry.register("slow_tool", "Test tool", {"type": "object"}, run_tool)
    agent = VDSSAgent(registry)
    monkeypatch.setattr(agent, "_llm_available", lambda: True)
    monkeypatch.setattr(agent.planner, "fast_path", lambda _message: None)
    monkeypatch.setattr(agent.planner, "plan", lambda _message: {"requires_tools": True})

    calls = []

    def request_tool(**kwargs):
        calls.append(kwargs)
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="slow_tool", arguments="{}"),
        )
        return SimpleNamespace(content="", tool_calls=[tool_call])

    monkeypatch.setattr("app.agent.agent.ask_llm", request_tool)

    with caplog.at_level(logging.INFO, logger="app.agent.agent"):
        response = agent.run(
            "private deadline-test message",
            deadline=10.0,
        )

    assert "time limit" in response
    assert len(calls) == 1
    assert calls[0]["timeout"] == 10.0
    assert "chat_tool_finished tool=slow_tool" in caplog.text
    assert "chat_deadline_exceeded stage=tool" in caplog.text
    assert "private deadline-test message" not in caplog.text


def test_agent_handles_sdk_timeout_explicitly_without_logging_chat_content(monkeypatch, caplog):
    agent = VDSSAgent(create_default_registry())
    monkeypatch.setattr(agent, "_llm_available", lambda: True)
    monkeypatch.setattr(agent, "_run_without_llm", lambda *_args: "existing fallback")
    monkeypatch.setattr(
        "app.agent.agent.ask_llm",
        lambda **_kwargs: (_ for _ in ()).throw(
            APITimeoutError(request=httpx.Request("POST", "https://openrouter.ai"))
        ),
    )

    with caplog.at_level(logging.WARNING, logger="app.agent.agent"):
        response = agent.run("private timeout-test message")

    assert response == "existing fallback"
    assert "outcome=timeout" in caplog.text
    assert "APITimeoutError" in caplog.text
    assert "private timeout-test message" not in caplog.text


@pytest.mark.parametrize(
    ("provider_error", "expected_category"),
    [
        (
            APIConnectionError(request=httpx.Request("POST", "https://openrouter.ai")),
            "outcome=connection_error",
        ),
        (
            APIStatusError(
                "provider failure",
                response=httpx.Response(
                    503,
                    request=httpx.Request("POST", "https://openrouter.ai"),
                ),
                body=None,
            ),
            "outcome=provider_error status_code=503",
        ),
    ],
)
def test_agent_preserves_fallback_for_provider_errors(
    monkeypatch,
    caplog,
    provider_error,
    expected_category,
):
    agent = VDSSAgent(create_default_registry())
    monkeypatch.setattr(agent, "_llm_available", lambda: True)
    monkeypatch.setattr(agent, "_run_without_llm", lambda *_args: "existing fallback")
    monkeypatch.setattr(
        "app.agent.agent.ask_llm",
        lambda **_kwargs: (_ for _ in ()).throw(provider_error),
    )

    with caplog.at_level(logging.WARNING, logger="app.agent.agent"):
        assert agent.run("private provider-error message") == "existing fallback"

    assert expected_category in caplog.text
    assert "private provider-error message" not in caplog.text


def test_agent_logs_model_call_timing_without_chat_content(monkeypatch, caplog):
    agent = VDSSAgent(create_default_registry())
    monkeypatch.setattr(agent, "_llm_available", lambda: True)
    monkeypatch.setattr(
        "app.agent.agent.ask_llm",
        lambda **_kwargs: SimpleNamespace(content="A response.", tool_calls=[]),
    )

    with caplog.at_level(logging.INFO, logger="app.agent.agent"):
        assert agent.run("private timing-test message") == "A response."

    assert "chat_model_call_finished round=1 duration_ms=" in caplog.text
    assert "private timing-test message" not in caplog.text


def test_rag_embedding_fallback_is_logged_without_query_text(monkeypatch, caplog):
    monkeypatch.setattr(
        retriever,
        "create_embedding",
        lambda _query: (_ for _ in ()).throw(RuntimeError("private query text")),
    )
    monkeypatch.setattr(retriever, "search", lambda **kwargs: [])

    with caplog.at_level(logging.WARNING, logger="app.rag.retriever"):
        assert retriever.retrieve("private query text") == []

    assert "rag_embedding_fallback exception_type=RuntimeError" in caplog.text
    assert "private query text" not in caplog.text


def test_deterministic_calculator_path_returns_natural_result():
    agent = VDSSAgent(create_default_registry())
    result = agent.run("Calculate 25% of 480.")
    assert "120" in result


def test_executor_restricts_invalid_required_arguments():
    executor = ToolExecutor(create_default_registry())
    result = executor.execute("calculator", {})
    assert result["success"] is False
    assert "expression" in result["error"]


def test_agent_logs_llm_failure_and_uses_existing_fallback(monkeypatch, caplog):
    agent = VDSSAgent(create_default_registry())
    monkeypatch.setattr(agent, "_llm_available", lambda: True)

    def fail_request(**_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("app.agent.agent.ask_llm", fail_request)
    with caplog.at_level(logging.WARNING, logger="app.agent.agent"):
        response = agent.run("Calculate 25% of 480.")

    assert "120" in response
    assert "outcome=unexpected_error" in caplog.text


def test_executor_logs_unexpected_tool_failures(caplog):
    registry = ToolRegistry()
    registry.register("broken", "A failing test tool", {"type": "object"}, lambda: 1 / 0)

    with caplog.at_level(logging.ERROR, logger="app.agent.executor"):
        result = ToolExecutor(registry).execute("broken", {})

    assert result["success"] is False
    assert "unexpected error" in caplog.text


def test_llm_client_rejects_empty_provider_choices(monkeypatch):
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=create,
            ),
        ),
    )
    monkeypatch.setattr(llm_client, "client", fake_client)
    monkeypatch.setattr(llm_client, "OPENROUTER_API_KEY", "test-key")

    with pytest.raises(RuntimeError, match="no assistant response"):
        llm_client.ask_llm(
            messages=[],
            tools=[{"type": "function"}],
            timeout=12.5,
        )

    assert captured["temperature"] == 0.2
    assert captured["timeout"] == 12.5
    assert captured["model"] == llm_client.OPENROUTER_MODEL
    assert captured["tool_choice"] == "auto"


def test_tool_registry_rejects_duplicate_and_incomplete_definitions():
    registry = ToolRegistry()
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    }
    registry.register("echo", "Echo a value", schema, lambda value: value)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("echo", "A replacement", schema, lambda value: value)
    with pytest.raises(ValueError, match="declared in properties"):
        registry.register("invalid", "Invalid schema", {"type": "object", "required": ["value"]}, lambda: None)


def test_executor_rejects_blank_required_string_arguments():
    registry = ToolRegistry()
    registry.register(
        "echo",
        "Echo a value",
        {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
        lambda value: value,
    )

    result = ToolExecutor(registry).execute("echo", {"value": "  "})

    assert result["success"] is False
    assert "cannot be blank" in result["error"]


def test_calculator_limits_exponent_and_non_finite_results():
    from app.tools.calculator import calculator

    assert "Exponent is too large" in calculator("2 ** 1000000")
    assert "not finite" in calculator("1e308 * 1e308")
    assert "Only numeric values" in calculator("True + 1")


def test_document_tool_formatter_cites_pages_and_avoids_absence_claims():
    answer = VDSSAgent._format_tool_result("search_knowledge", [{
        "page_number": 4,
        "text": "def print_statement_x9(): return 42",
    }])
    missing = VDSSAgent._format_tool_result("search_knowledge", [])

    assert "Page 4" in answer
    assert "print_statement_x9" in answer
    assert "does not confirm" in missing
    assert "did not contain" not in missing
