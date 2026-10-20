import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from zipfile import ZIP_DEFLATED, ZipFile

from app.agent.agent import VDSSAgent
from app.agent.registry import ToolRegistry
from app.main import app
from app.rag import retriever, vector_store
from app.rag.document_loader import load_document, load_document_pages
from app.tools import file_reader
from app.tools import rag as rag_tools
import app.api.routes as routes
from app.api.dependencies import get_agent
from app.database import crud
from app.database.database import SessionLocal
from app.services import document_service
from app.tools import embeddings
from app.tools import pdf_reader


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


def test_ingestion_replaces_existing_filename_chunks(tmp_path, monkeypatch):
	monkeypatch.setattr(file_reader, "DATA_DIR", tmp_path)
	monkeypatch.setattr(vector_store, "STORE_FILE", tmp_path / "vectors.json")
	path = tmp_path / "repeat.txt"
	path.write_text("The first indexed version.", encoding="utf-8")
	monkeypatch.setattr(rag_tools, "create_embeddings", lambda texts: [[1.0, 0.0] for _ in texts])

	assert rag_tools.ingest_document(str(path))["success"] is True
	path.write_text("The replacement indexed version.", encoding="utf-8")
	assert rag_tools.ingest_document(str(path))["success"] is True

	documents = vector_store.get_all_documents()
	assert len(documents) == 1
	assert documents[0]["text"] == "The replacement indexed version."


def test_selected_document_agent_uses_filtered_retrieval(monkeypatch):
	calls = []
	monkeypatch.setattr(
		"app.agent.agent.retrieve",
		lambda query, top_k, filename: calls.append((query, filename)) or [
			{"text": "Deadlock is a condition where processes wait indefinitely.", "page_number": 2}
		],
	)
	agent = VDSSAgent(ToolRegistry())
	monkeypatch.setattr(agent, "_llm_available", lambda: False)

	response = agent.run("Explain deadlock", source_filename="os.pdf")

	assert calls == [("Explain deadlock", "os.pdf")]
	assert "Deadlock is a condition" in response
	assert "Page 2" in response


def test_selected_document_llm_failure_returns_retrieved_evidence(monkeypatch):
	monkeypatch.setattr(
		"app.agent.agent.retrieve",
		lambda *_args, **_kwargs: [{"text": "The uploaded notes define orbital resonance.", "page_number": 4}],
	)
	agent = VDSSAgent(ToolRegistry())
	monkeypatch.setattr(agent, "_llm_available", lambda: True)
	monkeypatch.setattr(agent.planner, "plan", lambda _message: {"requires_tools": False})
	monkeypatch.setattr("app.agent.agent.ask_llm", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
	monkeypatch.setattr(agent, "_run_without_llm", lambda *_args: "Unrelated general answer")

	response = agent.run("Explain orbital resonance", source_filename="notes.pdf")

	assert "The uploaded notes define orbital resonance." in response
	assert "Page 4" in response
	assert "Unrelated general answer" not in response


def test_selected_document_llm_receives_page_labeled_evidence(monkeypatch):
	captured = {}

	class Response:
		content = "The notes define orbital resonance as a repeating alignment. (Page 4)"
		tool_calls = []

	monkeypatch.setattr(
		"app.agent.agent.retrieve",
		lambda *_args, **_kwargs: [{"text": "Orbital resonance is a repeating alignment.", "page_number": 4}],
	)
	monkeypatch.setattr("app.agent.agent.ask_llm", lambda **kwargs: captured.update(kwargs) or Response())
	agent = VDSSAgent(ToolRegistry())
	monkeypatch.setattr(agent, "_llm_available", lambda: True)
	monkeypatch.setattr(agent.planner, "plan", lambda _message: {"requires_tools": False})

	answer = agent.run("What is orbital resonance?", source_filename="notes.pdf")
	evidence_message = next(
		item["content"] for item in captured["messages"]
		if "Retrieved excerpts:" in item.get("content", "")
	)

	assert "[Page 4]" in evidence_message
	assert "Orbital resonance is a repeating alignment." in evidence_message
	assert "Page 4" in answer
	assert captured["tools"] is None


def _write_text_pdf(path, page_texts):
	writer = PdfWriter()
	for text in page_texts:
		page = writer.add_blank_page(width=612, height=792)
		font = DictionaryObject({
			NameObject("/Type"): NameObject("/Font"),
			NameObject("/Subtype"): NameObject("/Type1"),
			NameObject("/BaseFont"): NameObject("/Helvetica"),
		})
		font_ref = writer._add_object(font)
		page[NameObject("/Resources")] = DictionaryObject({
			NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
		})
		stream = DecodedStreamObject()
		stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
		page[NameObject("/Contents")] = writer._add_object(stream)
	with path.open("wb") as output:
		writer.write(output)


def test_pdf_ingestion_preserves_all_page_numbers_and_chunks(tmp_path, monkeypatch):
	monkeypatch.setattr(pdf_reader, "DATA_DIR", tmp_path)
	monkeypatch.setattr(vector_store, "STORE_FILE", tmp_path / "vectors.json")
	path = tmp_path / "study.pdf"
	_write_text_pdf(path, [
		"First page definition",
		"Program listing def print_statement_x9",
		"Third page conclusion laterpage_x9",
	])
	monkeypatch.setattr(rag_tools, "create_embeddings", lambda texts: [[1.0, 0.0] for _ in texts])

	result = rag_tools.ingest_document(str(path))
	documents = vector_store.get_all_documents()

	assert result["success"] is True
	assert result["pages_processed"] == 3
	assert {item["page_number"] for item in documents} == {1, 2, 3}
	assert any("print_statement_x9" in item["text"] and item["page_number"] == 2 for item in documents)
	monkeypatch.setattr(retriever, "create_embedding", lambda _query: [])
	later_page = retriever.retrieve("What is laterpage_x9 on page 3?", filename="study.pdf")
	assert later_page and later_page[0]["page_number"] == 3
	assert "laterpage_x9" in later_page[0]["text"]

	agent = VDSSAgent(ToolRegistry())
	monkeypatch.setattr(agent, "_llm_available", lambda: False)
	answer = agent.run("What is laterpage_x9 on page 3?", source_filename="study.pdf")
	assert "Page 3" in answer
	assert "laterpage_x9" in answer


def test_pdf_reader_reports_unreadable_pdf_types(tmp_path, monkeypatch):
	monkeypatch.setattr(pdf_reader, "DATA_DIR", tmp_path)

	malformed = tmp_path / "malformed.pdf"
	malformed.write_bytes(b"not a pdf")
	with pytest.raises(ValueError, match="malformed or unreadable"):
		pdf_reader.read_pdf_pages(str(malformed))

	encrypted = tmp_path / "encrypted.pdf"
	writer = PdfWriter()
	writer.add_blank_page(width=612, height=792)
	writer.encrypt("secret")
	with encrypted.open("wb") as output:
		writer.write(output)
	with pytest.raises(ValueError, match="password-protected"):
		pdf_reader.read_pdf_pages(str(encrypted))

	empty = tmp_path / "empty.pdf"
	with empty.open("wb") as output:
		PdfWriter().write(output)
	with pytest.raises(ValueError, match="no pages"):
		pdf_reader.read_pdf_pages(str(empty))

	scanned = tmp_path / "scanned.pdf"
	writer = PdfWriter()
	writer.add_blank_page(width=612, height=792)
	with scanned.open("wb") as output:
		writer.write(output)
	with pytest.raises(ValueError, match="scanned; OCR is not available"):
		pdf_reader.read_pdf_pages(str(scanned))


def test_retriever_uses_page_filter_and_exact_program_text(tmp_path, monkeypatch):
	monkeypatch.setattr(vector_store, "STORE_FILE", tmp_path / "vectors.json")
	monkeypatch.setattr(retriever, "create_embedding", lambda _query: (_ for _ in ()).throw(RuntimeError("offline")))
	vector_store.add_documents([
		{"id": "p1", "filename": "programs.pdf", "page_number": 1, "text": "Overview of algorithms", "embedding": [1.0, 0.0]},
		{"id": "p2", "filename": "programs.pdf", "page_number": 2, "text": "Program listing def print_statement_x9", "embedding": [0.0, 1.0]},
	])

	page_results = retriever.retrieve("find the program on page 2", filename="programs.pdf")
	code_results = retriever.retrieve("print_statement_x9", filename="programs.pdf")

	assert page_results and {item["page_number"] for item in page_results} == {2}
	assert code_results and code_results[0]["page_number"] == 2


def test_document_retrieval_miss_does_not_claim_content_is_absent(monkeypatch):
	monkeypatch.setattr("app.agent.agent.retrieve", lambda *_args, **_kwargs: [])
	agent = VDSSAgent(ToolRegistry())
	monkeypatch.setattr(agent, "_llm_available", lambda: False)

	response = agent.run("Find the source program", source_filename="programs.pdf")

	assert "does not confirm" in response
	assert "did not contain" not in response


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

		listed = client.get("/api/documents?q=ready.txt").json()
		assert len(listed) == 1
		assert listed[0]["filename"] == "ready.txt"
		assert listed[0]["status"] == "ready"
		assert listed[0]["file_type"] == "txt"
		opened = client.get("/api/documents/ready.txt/open")
		assert opened.status_code == 200
		assert opened.content == b"study text"

		replaced = client.post("/api/documents", files={"file": ("ready.txt", b"updated study text")})
		assert replaced.status_code == 200
		assert (tmp_path / "ready.txt").read_bytes() == b"updated study text"
		assert len(client.get("/api/documents?q=ready.txt").json()) == 1

		monkeypatch.setattr(routes, "ingest_document", lambda _path: {"success": False, "error": "internal detail"})
		failed = client.post("/api/documents", files={"file": ("failed.txt", b"bad document")})
		assert failed.status_code == 422
		assert failed.json()["detail"] == "internal detail"
		assert not (tmp_path / "failed.txt").exists()

		removed = client.delete("/api/documents/ready.txt")
		assert removed.status_code == 200
		assert not (tmp_path / "ready.txt").exists()
		assert deleted[-1] == "ready.txt"
		assert deleted.count("ready.txt") == 3
		repeated = client.delete("/api/documents/ready.txt")
		assert repeated.status_code == 200

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


def test_attachment_upload_returns_actionable_ingestion_error(tmp_path, monkeypatch):
	monkeypatch.setattr(routes, "CHAT_ATTACHMENTS_DIR", tmp_path / "chat-attachments")
	monkeypatch.setattr(
		routes,
		"ingest_document",
		lambda *_args, **_kwargs: {
			"success": False,
			"error": "No selectable text was found. The PDF may be scanned; OCR is not available.",
		},
	)
	db = SessionLocal()
	conversation = crud.create_conversation(db, user_id=1, title="Failed upload test")
	conversation_id = conversation.id
	db.close()
	try:
		with TestClient(app) as client:
			response = client.post(
				"/api/chat/attachments",
				data={"message": "Summarize this PDF", "conversation_id": conversation_id},
				files={"file": ("scan.pdf", b"pdf bytes")},
			)
		assert response.status_code == 422
		assert response.json()["detail"] == (
			"No selectable text was found. The PDF may be scanned; OCR is not available."
		)
		assert list((tmp_path / "chat-attachments").rglob("*.pdf")) == []
	finally:
		db = SessionLocal()
		crud.delete_conversation(db, conversation_id, user_id=1)
		db.close()


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
	indexed = []
	monkeypatch.setattr(routes, "get_all_documents", lambda: [{"filename": name} for name in indexed])
	monkeypatch.setattr(
		routes,
		"delete_documents_by_filename",
		lambda filename: indexed.remove(filename) if filename in indexed else 0,
	)
	def ingest(path, **kwargs):
		ingested.append((path, kwargs))
		indexed.append(path.rsplit("\\", 1)[-1])
		return {"success": True, "chunks_added": 1}
	monkeypatch.setattr(routes, "ingest_document", ingest)
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
			listed = client.get("/api/documents").json()
			attachments = [
				item for item in listed
				if item.get("storage_type") == "attachment" and item["conversation_id"] == conversation_id
			]
			assert len(attachments) == 1
			assert attachments[0]["filename"] == "os notes.txt"
			assert attachments[0]["status"] == "ready"
			assert attachments[0]["source"] == calls[0]["source_filename"]

			conversation = client.get(f"/api/conversations/{conversation_id}").json()
			assert "os notes.txt" in conversation["messages"][0]["content"]
			follow_up = client.post("/api/chat", json={
				"message": "What does it say about deadlocks?",
				"conversation_id": conversation_id,
			})
			assert follow_up.status_code == 200
			assert calls[1]["source_filename"] == calls[0]["source_filename"]

			duplicate = client.post(
				"/api/chat/attachments",
				data={"message": "Explain this other copy", "conversation_id": conversation_id},
				files={"file": ("os notes.txt", b"Different attachment content")},
			)
			assert duplicate.status_code == 200
			listed = client.get("/api/documents").json()
			attachments = [
				item for item in listed
				if item.get("storage_type") == "attachment" and item["conversation_id"] == conversation_id
			]
			assert len(attachments) == 2
			assert len({item["source"] for item in attachments}) == 2

			first, second = attachments
			first_path = tmp_path / "chat-attachments" / str(conversation_id) / first["source"]
			ambiguous_legacy_delete = client.delete("/api/documents/os%20notes.txt")
			assert ambiguous_legacy_delete.status_code == 409
			assert first_path.is_file()
			unauthorized = client.delete(
				f"/api/documents/attachments/{conversation_id + 100000}/{first['source']}"
			)
			assert unauthorized.status_code == 404
			assert first_path.is_file()
			removed = client.delete(first["delete_url"])
			assert removed.status_code == 200
			assert not first_path.exists()
			assert first["source"] not in indexed
			assert [
				item["source"] for item in client.get("/api/documents").json()
				if item.get("storage_type") == "attachment" and item["conversation_id"] == conversation_id
			] == [second["source"]]

			second_path = tmp_path / "chat-attachments" / str(conversation_id) / second["source"]
			second_path.unlink()
			missing = next(item for item in client.get("/api/documents").json() if item.get("source") == second["source"])
			assert missing["status"] == "missing"
			removed_missing = client.delete(missing["delete_url"])
			assert removed_missing.status_code == 200
			assert second["source"] not in indexed
			assert all(item.get("source") != second["source"] for item in client.get("/api/documents").json())

			unique = client.post(
				"/api/chat/attachments",
				data={"message": "Explain the unique copy", "conversation_id": conversation_id},
				files={"file": ("single note.txt", b"Unique attachment content")},
			)
			assert unique.status_code == 200
			unique_source = calls[-1]["source_filename"]
			unique_path = tmp_path / "chat-attachments" / str(conversation_id) / unique_source
			legacy_delete = client.delete("/api/documents/single%20note.txt")
			assert legacy_delete.status_code == 200
			assert not unique_path.exists()
			assert unique_source not in indexed
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


def test_cosine_similarity_handles_large_finite_vectors():
	score = vector_store.cosine_similarity([1e308, 1e308], [1e308, 0.0])

	assert score == pytest.approx(2 ** -0.5)


def test_vector_store_serializes_concurrent_additions(tmp_path, monkeypatch):
	monkeypatch.setattr(vector_store, "STORE_FILE", tmp_path / "vectors.json")

	def add_document(index):
		return vector_store.add_documents([{
			"id": str(index),
			"filename": f"notes-{index}.txt",
			"embedding": [1.0, 0.0],
		}])

	with ThreadPoolExecutor(max_workers=6) as executor:
		assert sum(executor.map(add_document, range(24))) == 24

	assert len(vector_store.get_all_documents()) == 24
	assert not list(tmp_path.glob("*.tmp"))


def test_embedding_rejects_non_finite_model_output(monkeypatch):
	class VectorBatch:
		def __len__(self):
			return 1

		def tolist(self):
			return [[1.0, float("inf")]]

	class FakeModel:
		def encode(self, _texts, **_kwargs):
			return VectorBatch()

	monkeypatch.setattr(embeddings, "get_embedding_model", lambda: FakeModel())
	with pytest.raises(RuntimeError, match="non-finite"):
		embeddings.create_embedding("valid input")


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