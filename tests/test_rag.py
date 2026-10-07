import json
import pytest
from fastapi.testclient import TestClient
from zipfile import ZIP_DEFLATED, ZipFile

from app.agent.agent import VDSSAgent
from app.agent.registry import ToolRegistry
from app.main import app
from app.rag import retriever, vector_store
from app.rag.document_loader import load_document
from app.tools import file_reader
from app.tools import rag as rag_tools
import app.api.routes as routes
from app.api.dependencies import get_agent
from app.database import crud
from app.database.database import SessionLocal
from app.services import document_service
from app.tools import embeddings


def test_retriever_limits_results_to_selected_filename(tmp_path, monkeypatch):
	monkeypatch.setattr(vector_store, "STORE_FILE", tmp_path / "vectors.json")
	monkeypatch.setattr(retriever, "create_embedding", lambda _query: [1.0, 0.0])
	vector_store.add_documents([
		{"id": "1", "filename": "os.pdf", "text": "Deadlock in operating systems", "embedding": [1.0, 0.0]},
		{"id": "2", "filename": "dbms.pdf", "text": "Database normalization", "embedding": [1.0, 0.0]},
		{"id": "3", "filename": "attachment_private.txt", "text": "Private conversation material", "embedding": [1.0, 0.0], "private": True},
	])

	results = retriever.retrieve("deadlock", filename="os.pdf")

	assert [item["filename"] for item in results] == ["os.pdf"]
	assert all(item["filename"] != "attachment_private.txt" for item in retriever.retrieve("material"))
	assert [item["filename"] for item in retriever.retrieve("material", filename="attachment_private.txt")] == ["attachment_private.txt"]
	assert vector_store.delete_documents_by_filename("os.pdf") == 1
	assert {item["filename"] for item in vector_store.get_all_documents()} == {"dbms.pdf", "attachment_private.txt"}


def test_existing_docx_loader_extracts_paragraph_text(tmp_path):
	path = tmp_path / "notes.docx"
	document_xml = (
		'<?xml version="1.0" encoding="UTF-8"?>'
		'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
		'<w:body><w:p><w:r><w:t>Operating systems notes</w:t></w:r></w:p></w:body>'
		'</w:document>'
	)
	with ZipFile(path, "w", ZIP_DEFLATED) as archive:
		archive.writestr("word/document.xml", document_xml)

	assert load_document(str(path)) == "Operating systems notes"


def test_ingestion_uses_existing_loader_chunker_and_vector_store(tmp_path, monkeypatch):
	monkeypatch.setattr(file_reader, "DATA_DIR", tmp_path)
	path = tmp_path / "study.txt"
	path.write_text("Processes can deadlock while waiting for resources.", encoding="utf-8")
	stored = []
	monkeypatch.setattr(rag_tools, "create_embeddings", lambda texts: [[1.0, 0.0] for _ in texts])
	monkeypatch.setattr(rag_tools, "add_documents", lambda documents: stored.extend(documents) or len(documents))

	result = rag_tools.ingest_document(str(path))

	assert result["success"] is True
	assert result["chunks_added"] == 1
	assert stored[0]["filename"] == "study.txt"
	assert "deadlock" in stored[0]["text"]


def test_selected_document_agent_uses_filtered_retrieval(monkeypatch):
	calls = []
	monkeypatch.setattr(
		"app.agent.agent.retrieve",
		lambda query, top_k, filename: calls.append((query, filename)) or [
			{"text": "Deadlock is a condition where processes wait indefinitely."}
		],
	)
	agent = VDSSAgent(ToolRegistry())
	monkeypatch.setattr(agent, "_llm_available", lambda: False)

	response = agent.run("Explain deadlock", source_filename="os.pdf")

	assert calls == [("Explain deadlock", "os.pdf")]
	assert "Deadlock is a condition" in response


def test_document_upload_list_failure_and_individual_delete(tmp_path, monkeypatch):
	monkeypatch.setattr(routes, "DOCUMENTS_DIR", tmp_path)
	deleted = []
	monkeypatch.setattr(routes, "delete_documents_by_filename", deleted.append)
	monkeypatch.setattr(routes, "get_all_documents", lambda: [{"filename": "ready.txt"}])
	monkeypatch.setattr(routes, "ingest_document", lambda _path: {"success": True, "chunks_added": 1})

	with TestClient(app) as client:
		uploaded = client.post("/api/documents", files={"file": ("ready.txt", b"study text")})
		assert uploaded.status_code == 200
		assert uploaded.json()["status"] == "ready"

		listed = client.get("/api/documents").json()
		assert listed[0]["filename"] == "ready.txt"
		assert listed[0]["status"] == "ready"
		assert listed[0]["file_type"] == "txt"
		opened = client.get("/api/documents/ready.txt/open")
		assert opened.status_code == 200
		assert opened.content == b"study text"

		monkeypatch.setattr(routes, "ingest_document", lambda _path: {"success": False, "error": "internal detail"})
		failed = client.post("/api/documents", files={"file": ("failed.txt", b"bad document")})
		assert failed.status_code == 422
		assert failed.json()["detail"] == "Could not process this document"

		removed = client.delete("/api/documents/ready.txt")
		assert removed.status_code == 200
		assert not (tmp_path / "ready.txt").exists()
		assert deleted[-1] == "ready.txt"
		assert deleted.count("ready.txt") == 2

		unsupported = client.post("/api/documents", files={"file": ("bad.exe", b"no")})
		assert unsupported.status_code == 400


def test_failed_document_replacement_restores_file_and_index(tmp_path, monkeypatch):
	monkeypatch.setattr(routes, "DOCUMENTS_DIR", tmp_path)
	stored = [{"filename": "study.txt", "text": "previous index", "embedding": [1.0]}]

	def delete_documents(filename):
		stored[:] = [item for item in stored if item["filename"] != filename]

	monkeypatch.setattr(routes, "get_all_documents", lambda: list(stored))
	monkeypatch.setattr(routes, "delete_documents_by_filename", delete_documents)
	monkeypatch.setattr(routes, "add_documents", lambda documents: stored.extend(documents))
	monkeypatch.setattr(routes, "ingest_document", lambda _path: {"success": False})
	(tmp_path / "study.txt").write_bytes(b"previous file")

	with TestClient(app) as client:
		response = client.post("/api/documents", files={"file": ("study.txt", b"replacement")})

	assert response.status_code == 422
	assert (tmp_path / "study.txt").read_bytes() == b"previous file"
	assert stored == [{"filename": "study.txt", "text": "previous index", "embedding": [1.0]}]


def test_chat_and_note_requests_reject_blank_text():
	with TestClient(app) as client:
		assert client.post("/api/chat", json={"message": "   "}).status_code == 422
		assert client.post("/api/notes", json={"title": "  ", "content": "note"}).status_code == 422


def test_attachment_chat_rejects_invalid_preferences_before_writing_files(tmp_path, monkeypatch):
	monkeypatch.setattr(routes, "CHAT_ATTACHMENTS_DIR", tmp_path)
	with TestClient(app) as client:
		response = client.post(
			"/api/chat/attachments",
			data={"message": "Explain this", "preferences": "not-json"},
			files={"file": ("notes.txt", b"study notes")},
		)
	assert response.status_code == 422
	assert list(tmp_path.iterdir()) == []


def test_vector_store_skips_malformed_rows_and_invalid_search_limits(tmp_path, monkeypatch):
	monkeypatch.setattr(vector_store, "STORE_FILE", tmp_path / "vectors.json")
	vector_store.STORE_FILE.write_text(json.dumps([
		"not a document",
		{"filename": "bad.txt", "embedding": [float("nan")]},
		{"filename": "good.txt", "embedding": [1.0, 0.0], "text": "usable"},
	]), encoding="utf-8")

	assert [item["filename"] for item in vector_store.search([1.0, 0.0])] == ["good.txt"]
	assert vector_store.search([1.0, 0.0], top_k=0) == []
	with pytest.raises(ValueError, match="minimum_score"):
		retriever.retrieve("query", minimum_score=float("nan"))


def test_embedding_rejects_blank_text_without_loading_model(monkeypatch):
	monkeypatch.setattr(embeddings, "get_embedding_model", lambda: pytest.fail("model should not load"))
	with pytest.raises(ValueError, match="cannot be blank"):
		embeddings.create_embedding("   ")


def test_document_service_rejects_unsafe_and_missing_names(tmp_path, monkeypatch):
	monkeypatch.setattr(document_service, "DOCUMENTS_DIR", tmp_path)
	assert document_service.ingest_document_by_name("../outside.txt")["success"] is False
	assert document_service.ingest_document_by_name("missing.txt") == {
		"success": False,
		"error": "Document does not exist.",
	}


def test_chat_forwards_selected_document_to_existing_agent(tmp_path, monkeypatch):
	monkeypatch.setattr(routes, "DOCUMENTS_DIR", tmp_path)
	(tmp_path / "os.pdf").write_bytes(b"test document")
	captured = {}

	class Agent:
		def run(self, **kwargs):
			captured.update(kwargs)
			return "Answer grounded in OS notes."

	app.dependency_overrides[get_agent] = Agent
	db = SessionLocal()
	conversation = crud.create_conversation(db, user_id=1, title="Uploads test")
	conversation_id = conversation.id
	db.close()
	try:
		with TestClient(app) as client:
			response = client.post("/api/chat", json={
				"message": "Explain deadlock",
				"conversation_id": conversation_id,
				"source_filename": "os.pdf",
			})
		assert response.status_code == 200
		assert captured["source_filename"] == "os.pdf"
		assert response.json()["response"] == "Answer grounded in OS notes."
	finally:
		app.dependency_overrides.pop(get_agent, None)
		db = SessionLocal()
		crud.delete_conversation(db, conversation_id, user_id=1)
		db.close()


def test_chat_attachment_uses_existing_conversation_and_is_reused(tmp_path, monkeypatch):
	monkeypatch.setattr(routes, "CHAT_ATTACHMENTS_DIR", tmp_path / "chat-attachments")
	ingested = []
	monkeypatch.setattr(routes, "ingest_document", lambda path, **kwargs: ingested.append((path, kwargs)) or {"success": True, "chunks_added": 1})
	calls = []

	class Agent:
		def run(self, **kwargs):
			calls.append(kwargs)
			return "Answer grounded in the attachment."

	app.dependency_overrides[get_agent] = Agent
	db = SessionLocal()
	conversation = crud.create_conversation(db, user_id=1, title="Attachment test")
	conversation_id = conversation.id
	db.close()
	try:
		with TestClient(app) as client:
			response = client.post(
				"/api/chat/attachments",
				data={"message": "Explain this page", "conversation_id": conversation_id},
				files={"file": ("os notes.txt", b"Operating systems study notes")},
			)
			assert response.status_code == 200
			assert response.json()["conversation_id"] == conversation_id
			assert ingested[0][1] == {"private": True}
			assert calls[0]["user_message"] == "Explain this page"
			assert calls[0]["source_filename"].startswith("attachment_")
			assert calls[0]["conversation_messages"][-1]["content"] == "Explain this page"

			conversation = client.get(f"/api/conversations/{conversation_id}").json()
			assert "os notes.txt" in conversation["messages"][0]["content"]
			follow_up = client.post("/api/chat", json={
				"message": "What does it say about deadlocks?",
				"conversation_id": conversation_id,
			})
			assert follow_up.status_code == 200
			assert calls[1]["source_filename"] == calls[0]["source_filename"]
	finally:
		app.dependency_overrides.pop(get_agent, None)
		db = SessionLocal()
		crud.delete_conversation(db, conversation_id, user_id=1)
		db.close()


def test_study_plan_priority_persists_through_existing_api():
	with TestClient(app) as client:
		created = client.post("/api/study-plans", json={
			"title": "Priority persistence test",
			"subject": "Operating Systems",
			"priority": "high",
		})
		assert created.status_code == 200
		plan_id = created.json()["id"]
		try:
			assert created.json()["priority"] == "high"
			updated = client.patch(f"/api/study-plans/{plan_id}", json={"priority": "low"})
			assert updated.status_code == 200
			assert updated.json()["priority"] == "low"
			listed = client.get("/api/study-plans").json()
			assert next(plan for plan in listed if plan["id"] == plan_id)["priority"] == "low"
		finally:
			client.delete(f"/api/study-plans/{plan_id}")


def test_natural_language_study_plan_is_saved_as_daily_tasks():
	with TestClient(app) as client:
		response = client.post("/api/study-plans/from-request", json={
			"request": "I have 3 days to prepare for OS",
		})
		assert response.status_code == 200
		tasks = response.json()["tasks"]
		try:
			assert len(tasks) == 3
			assert {task["subject"] for task in tasks} == {"OS"}
			assert [task["priority"] for task in tasks] == ["medium"] * 3
			assert all(task["scheduled_at"] for task in tasks)
		finally:
			for task in tasks:
				client.delete(f"/api/study-plans/{task['id']}")


def test_notes_create_edit_search_and_delete_use_existing_api():
	with TestClient(app) as client:
		created = client.post("/api/notes", json={
			"title": "Workspace CRUD verification",
			"subject": "Regression QA",
			"content": "Notes should remain searchable by subject.",
		})
		assert created.status_code == 200
		note_id = created.json()["id"]
		try:
			updated = client.patch(f"/api/notes/{note_id}", json={"title": "Updated workspace note"})
			assert updated.status_code == 200
			assert updated.json()["title"] == "Updated workspace note"
			search = client.get("/api/notes?q=Regression%20QA").json()
			assert any(note["id"] == note_id for note in search)
		finally:
			deleted = client.delete(f"/api/notes/{note_id}")
			assert deleted.status_code == 200
