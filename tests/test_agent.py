from fastapi.testclient import TestClient

from app.agent.executor import ToolExecutor
from app.agent.registry import create_default_registry
from app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_chat_without_llm_key_returns_controlled_response():
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "Explain binary search in simple terms."})
        assert response.status_code == 200
        assert "response" in response.json()
        assert isinstance(response.json()["response"], str)


def test_executor_rejects_unknown_and_invalid_tools():
    registry = create_default_registry()
    executor = ToolExecutor(registry)

    unknown = executor.execute("missing_tool", {})
    assert isinstance(unknown, dict)
    assert unknown["success"] is False

    invalid = executor.execute("calculator", '{invalid json')
    assert isinstance(invalid, dict)
    assert invalid["success"] is False
