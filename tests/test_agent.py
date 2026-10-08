from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.agent.executor import ToolExecutor
from app.agent.registry import create_default_registry
import app.database.database as database
from app.api.dependencies import get_agent
from app.api.schemas import NoteUpdate
from app.main import app, create_app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_database_initialization_runs_during_application_startup(monkeypatch):
    import app.main as main_module
    initialized = []
    monkeypatch.setattr(main_module, "create_tables", lambda: initialized.append(True))

    with TestClient(create_app()):
        assert initialized == [True]


def test_database_session_rolls_back_when_endpoint_raises(monkeypatch):
    session = Mock()
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    dependency = database.get_db()
    assert next(dependency) is session

    with pytest.raises(RuntimeError, match="request failed"):
        dependency.throw(RuntimeError("request failed"))

    session.rollback.assert_called_once()
    session.close.assert_called_once()


def test_chat_without_llm_key_returns_controlled_response():
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "Explain binary search in simple terms."})
        try:
            assert response.status_code == 200
            assert "response" in response.json()
            assert isinstance(response.json()["response"], str)
        finally:
            if response.status_code == 200:
                client.delete(f"/api/conversations/{response.json()['conversation_id']}")


def test_executor_rejects_unknown_and_invalid_tools():
    registry = create_default_registry()
    executor = ToolExecutor(registry)

    unknown = executor.execute("missing_tool", {})
    assert isinstance(unknown, dict)
    assert unknown["success"] is False

    invalid = executor.execute("calculator", '{invalid json')
    assert isinstance(invalid, dict)
    assert invalid["success"] is False

def test_chat_rejects_nonpositive_conversation_ids():
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "hello", "conversation_id": 0})

    assert response.status_code == 422


def test_note_update_rejects_explicit_null_for_required_fields():
    with pytest.raises(ValueError, match="cannot be null"):
        NoteUpdate.model_validate({"title": None})


def test_settings_validation_rejects_unknown_application_environment(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "staging")

    with pytest.raises(ValueError, match="APP_ENV"):
        settings.validate_settings()


def test_chat_agent_failure_returns_friendly_error_without_exception_details():
    class BrokenAgent:
        def run(self, **_kwargs):
            raise RuntimeError("provider secret detail")

    with TestClient(app) as client:
        conversation_id = client.post("/api/conversations", json={"title": "Failure test"}).json()["id"]
        app.dependency_overrides[get_agent] = BrokenAgent
        try:
            response = client.post("/api/chat", json={
                "message": "Explain a topic",
                "conversation_id": conversation_id,
            })
            assert response.status_code == 503
            assert response.json()["detail"] == "SAGE could not complete that request. Please try again."
            assert "provider secret detail" not in response.text
        finally:
            app.dependency_overrides.pop(get_agent, None)
            client.delete(f"/api/conversations/{conversation_id}")
