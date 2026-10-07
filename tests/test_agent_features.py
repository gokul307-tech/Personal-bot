import logging
from types import SimpleNamespace

import pytest
from app.agent.agent import VDSSAgent
from app.agent.planner import AgentPlanner
from app.agent.registry import create_default_registry
from app.agent.executor import ToolExecutor
from app.agent.registry import ToolRegistry
from app.llm import client as llm_client


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
    with caplog.at_level(logging.ERROR, logger="app.agent.agent"):
        response = agent.run("Calculate 25% of 480.")

    assert "120" in response
    assert "Language-model request failed" in caplog.text


def test_executor_logs_unexpected_tool_failures(caplog):
    registry = ToolRegistry()
    registry.register("broken", "A failing test tool", {"type": "object"}, lambda: 1 / 0)

    with caplog.at_level(logging.ERROR, logger="app.agent.executor"):
        result = ToolExecutor(registry).execute("broken", {})

    assert result["success"] is False
    assert "unexpected error" in caplog.text


def test_llm_client_rejects_empty_provider_choices(monkeypatch):
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_kwargs: SimpleNamespace(choices=[]),
            ),
        ),
    )
    monkeypatch.setattr(llm_client, "client", fake_client)
    monkeypatch.setattr(llm_client, "OPENROUTER_API_KEY", "test-key")

    with pytest.raises(RuntimeError, match="no assistant response"):
        llm_client.ask_llm(messages=[])
