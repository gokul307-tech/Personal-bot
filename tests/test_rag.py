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


def test_retriever_limits_results_to_selected_filename(tmp_path, monkeypatch):
	monkeypatch.setattr(vector_store, "STORE_FILE", tmp_path / "vectors.json")
	monkeypatch.setattr(retriever, "create_embedding", lambda _query: [1.0, 0.0])
	vector_store.add_documents([
		{"id": "1", "filename": "os.pdf", "text": "Deadlock in operating systems", "embedding": [1.0, 0.0]},
		{"id": "2", "filename": "dbms.pdf", "text": "Database normalization", "embedding": [1.0, 0.0]},
	])

	results = retriever.retrieve("deadlock", filename="os.pdf")

	assert [item["filename"] for item in results] == ["os.pdf"]
	assert vector_store.delete_documents_by_filename("os.pdf") == 1
	assert [item["filename"] for item in vector_store.get_all_documents()] == ["dbms.pdf"]


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
	monkeypatch.setattr(routes, "ingest_document", lambda _path: {"success": True, "chunks_added": 1})
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
