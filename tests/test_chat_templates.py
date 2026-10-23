from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.agent import VDSSAgent
from app.agent.registry import ToolRegistry
from app.api import routes
from app.api.dependencies import get_agent
from app.database import crud
from app.database.database import Base
from app.main import app


def _database(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def get_test_db():
        yield factory()

    monkeypatch.setattr(routes, "get_db", get_test_db)
    return engine, factory


def test_new_chat_persists_template_and_existing_conversation_keeps_it(monkeypatch):
    _engine, factory = _database(monkeypatch)
    captured = []

    class Agent:
        def run(self, **kwargs):
            captured.append(kwargs)
            return "Response"

    app.dependency_overrides[get_agent] = Agent
    try:
        with TestClient(app) as client:
            default_response = client.post("/api/chat", json={"message": "Hello"})
            assert default_response.status_code == 200
            default_id = default_response.json()["conversation_id"]
            assert client.get(f"/api/conversations/{default_id}").json()["template"] == "general"
            assert captured[-1]["conversation_template"] == "general"

            db = factory()
            existing = crud.create_conversation(db, user_id=1, title="Tutor chat", template="study")
            crud.add_message(db, existing.id, "user", "Keep this history")
            existing_id = existing.id
            db.close()

            response = client.post("/api/chat", json={
                "message": "Continue teaching me",
                "conversation_id": existing_id,
                "template": "coding",
            })
            assert response.status_code == 200
            conversation = client.get(f"/api/conversations/{existing_id}").json()
            assert conversation["template"] == "study"
            assert conversation["messages"][0]["content"] == "Keep this history"
            assert captured[-1]["conversation_template"] == "study"
    finally:
        app.dependency_overrides.pop(get_agent, None)


def test_conversation_create_api_supports_templates_and_default(monkeypatch):
    _database(monkeypatch)
    with TestClient(app) as client:
        default = client.post("/api/conversations", json={"title": "Default"})
        document = client.post("/api/conversations", json={
            "title": "Document chat",
            "template": "document",
        })

        assert default.status_code == 200
        assert default.json()["template"] == "general"
        assert document.status_code == 200
        assert document.json()["template"] == "document"
        assert client.get(f"/api/conversations/{document.json()['id']}").json()["template"] == "document"


def test_selected_template_is_saved_for_new_chat(monkeypatch):
    _engine, _factory = _database(monkeypatch)
    captured = {}

    class Agent:
        def run(self, **kwargs):
            captured.update(kwargs)
            return "Coding answer"

    app.dependency_overrides[get_agent] = Agent
    try:
        with TestClient(app) as client:
            response = client.post("/api/chat", json={
                "message": "Help debug this function",
                "template": "coding",
            })
            assert response.status_code == 200
            conversation = client.get(f"/api/conversations/{response.json()['conversation_id']}").json()
            assert conversation["template"] == "coding"
            assert captured["conversation_template"] == "coding"
    finally:
        app.dependency_overrides.pop(get_agent, None)


def test_attachment_created_conversation_persists_selected_template(tmp_path, monkeypatch):
    _database(monkeypatch)
    monkeypatch.setattr(routes, "CHAT_ATTACHMENTS_DIR", tmp_path / "chat-attachments")
    monkeypatch.setattr(routes, "ingest_document", lambda *_args, **_kwargs: {"success": True, "chunks_added": 1})
    calls = []

    class Agent:
        def run(self, **kwargs):
            calls.append(kwargs)
            return "Document answer"

    app.dependency_overrides[get_agent] = Agent
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/chat/attachments",
                data={"message": "Explain this", "template": "document"},
                files={"file": ("notes.txt", b"Attached notes")},
            )
            assert response.status_code == 200
            conversation_id = response.json()["conversation_id"]
            conversation = client.get(f"/api/conversations/{conversation_id}").json()
            assert conversation["template"] == "document"
            assert calls[0]["conversation_template"] == "document"
    finally:
        app.dependency_overrides.pop(get_agent, None)


def test_templates_change_agent_instructions(monkeypatch):
    expected = {
        "general": None,
        "study": "step-by-step",
        "coding": "debugging",
        "document": "attached to or selected in this conversation",
    }
    monkeypatch.setattr(VDSSAgent, "_llm_available", lambda _self: True)
    monkeypatch.setattr(VDSSAgent, "_run_without_llm", lambda *_args: "fallback")

    for template, phrase in expected.items():
        captured = {}

        def ask_llm(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content="Done", tool_calls=[])

        monkeypatch.setattr("app.agent.agent.ask_llm", ask_llm)
        agent = VDSSAgent(ToolRegistry())
        monkeypatch.setattr(agent.planner, "plan", lambda _message: {"requires_tools": False})
        response = agent.run("Help with this", conversation_template=template)
        if template == "document":
            assert "Attach or select a document" in response
            assert captured == {}
            continue
        system_message = captured["messages"][0]["content"]
        if phrase is None:
            assert "Conversation template:" not in system_message
        else:
            assert phrase in system_message


def test_legacy_conversations_get_general_template_without_data_loss(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE conversations (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "title VARCHAR(255) NOT NULL, created_at DATETIME, updated_at DATETIME)"
        ))
        connection.execute(text(
            "INSERT INTO conversations (id, user_id, title) VALUES (1, 1, 'Existing')"
        ))
    monkeypatch.setattr("app.database.database.engine", engine)

    from app.database.database import create_tables

    create_tables()

    columns = {column["name"] for column in inspect(engine).get_columns("conversations")}
    with engine.connect() as connection:
        row = connection.execute(text("SELECT title, template FROM conversations WHERE id = 1")).one()
    assert "template" in columns
    assert row == ("Existing", "general")