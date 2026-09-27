from app.agent.agent import VDSSAgent
from app.agent.planner import AgentPlanner
from app.agent.registry import create_default_registry
from app.agent.executor import ToolExecutor


def test_planner_classifies_exam_and_calculator_intent():
    planner = AgentPlanner()
    plan = planner.plan("Give me a 5 mark answer for Round Robin scheduling.")
    assert plan["intent"] == "study_question"
    assert plan["exam_mode"] == "5-mark"

    arguments = planner.build_tool_arguments("Calculate 25% of 480.", "calculator")
    assert arguments["expression"] == "(25 / 100) * (480)"


def test_deterministic_calculator_path_returns_natural_result():
    agent = VDSSAgent(create_default_registry())
    result = agent.run("Calculate 25% of 480.")
    assert "120" in result


def test_executor_restricts_invalid_required_arguments():
    executor = ToolExecutor(create_default_registry())
    result = executor.execute("calculator", {})
    assert result["success"] is False
    assert "expression" in result["error"]
