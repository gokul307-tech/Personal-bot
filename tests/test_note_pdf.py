from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes
from app.database.database import Base
from app.main import app
from app.tools import pdf_reader


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


def _write_text_pdf(path: Path, text: str = "Persisted note PDF text") -> None:
    writer = PdfWriter()
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


def _upload_note(client, filename="lecture.pdf", content=b"placeholder"):
    return client.post(
        "/api/notes/with-pdf",
        data={"title": "Lecture note", "content": "Review the attached handout", "subject": "Biology"},
        files={"file": (filename, content, "application/pdf")},
    )


def test_note_pdf_upload_list_and_view_on_followup_request(tmp_path, monkeypatch):
    _database(monkeypatch)
    monkeypatch.setattr(routes, "NOTE_ATTACHMENTS_DIR", tmp_path / "uploads" / "note-attachments")
    monkeypatch.setattr(pdf_reader, "DATA_DIR", tmp_path)
    pdf_path = tmp_path / "valid.pdf"
    _write_text_pdf(pdf_path)

    with TestClient(app) as client:
        uploaded = _upload_note(client, content=pdf_path.read_bytes())
        assert uploaded.status_code == 200
        note = uploaded.json()
        assert note["pdf_filename"] == "lecture.pdf"
        stored_files = list((tmp_path / "uploads" / "note-attachments").glob("*.pdf"))
        assert len(stored_files) == 1

        listed = client.get("/api/notes?q=lecture.pdf").json()
        assert len(listed) == 1
        assert listed[0]["id"] == note["id"]
        assert listed[0]["pdf_filename"] == "lecture.pdf"

        viewed = client.get(f"/api/notes/{note['id']}/pdf")
        assert viewed.status_code == 200
        assert "inline" in viewed.headers["content-disposition"]
        assert viewed.content == pdf_path.read_bytes()

        refreshed = client.get("/api/notes").json()
        assert refreshed[0]["pdf_filename"] == "lecture.pdf"


def test_note_pdfs_have_a_separate_uploads_list(tmp_path, monkeypatch):
    _database(monkeypatch)
    monkeypatch.setattr(routes, "NOTE_ATTACHMENTS_DIR", tmp_path / "uploads" / "note-attachments")
    monkeypatch.setattr(routes, "DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr(routes, "get_all_documents", lambda: [])
    monkeypatch.setattr(pdf_reader, "DATA_DIR", tmp_path)
    pdf_path = tmp_path / "handout.pdf"
    _write_text_pdf(pdf_path)

    with TestClient(app) as client:
        uploaded = _upload_note(client, filename="handout.pdf", content=pdf_path.read_bytes())
        note = uploaded.json()

        listed = client.get("/api/notes/pdfs")
        assert listed.status_code == 200
        assert listed.json() == [{
            "note_id": note["id"],
            "note_title": "Lecture note",
            "filename": "handout.pdf",
            "status": "ready",
            "size": len(pdf_path.read_bytes()),
            "uploaded_at": note["created_at"],
            "view_url": f"/api/notes/{note['id']}/pdf",
            "delete_url": f"/api/notes/{note['id']}/pdf",
        }]

        documents = client.get("/api/documents").json()
        assert all(item.get("filename") != "handout.pdf" for item in documents)

        deleted = client.delete(listed.json()[0]["delete_url"])
        assert deleted.status_code == 200
        assert client.get("/api/notes/pdfs").json() == []


@pytest.mark.parametrize(("pdf_bytes", "expected_detail"), [
    (b"not a PDF", "This PDF is malformed or unreadable."),
    (b"", "The PDF file is empty."),
])
def test_note_pdf_rejects_invalid_or_empty_files_without_orphans(tmp_path, monkeypatch, pdf_bytes, expected_detail):
    _database(monkeypatch)
    monkeypatch.setattr(routes, "NOTE_ATTACHMENTS_DIR", tmp_path / "uploads" / "note-attachments")
    monkeypatch.setattr(pdf_reader, "DATA_DIR", tmp_path)

    with TestClient(app) as client:
        response = _upload_note(client, content=pdf_bytes)

    assert response.status_code == 422
    assert response.json()["detail"] == expected_detail
    assert not routes.NOTE_ATTACHMENTS_DIR.exists() or list(routes.NOTE_ATTACHMENTS_DIR.iterdir()) == []
    db = next(routes.get_db())
    try:
        assert db.query(routes.Note).count() == 0
    finally:
        db.close()


def test_note_pdf_rejects_password_protected_file(tmp_path, monkeypatch):
    _database(monkeypatch)
    monkeypatch.setattr(routes, "NOTE_ATTACHMENTS_DIR", tmp_path / "uploads" / "note-attachments")
    monkeypatch.setattr(pdf_reader, "DATA_DIR", tmp_path)
    encrypted_path = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    with encrypted_path.open("wb") as output:
        writer.write(output)

    with TestClient(app) as client:
        response = _upload_note(client, content=encrypted_path.read_bytes())

    assert response.status_code == 422
    assert response.json()["detail"] == "This PDF is password-protected. Remove the password and upload it again."
    assert not routes.NOTE_ATTACHMENTS_DIR.exists() or list(routes.NOTE_ATTACHMENTS_DIR.iterdir()) == []


def test_note_pdf_and_note_deletion_clean_only_their_attachment(tmp_path, monkeypatch):
    _database(monkeypatch)
    monkeypatch.setattr(routes, "NOTE_ATTACHMENTS_DIR", tmp_path / "uploads" / "note-attachments")
    monkeypatch.setattr(pdf_reader, "DATA_DIR", tmp_path)
    pdf_path = tmp_path / "valid.pdf"
    _write_text_pdf(pdf_path)
    unrelated = routes.NOTE_ATTACHMENTS_DIR / "unrelated.pdf"
    routes.NOTE_ATTACHMENTS_DIR.mkdir(parents=True)
    unrelated.write_bytes(b"leave untouched")

    with TestClient(app) as client:
        uploaded = _upload_note(client, content=pdf_path.read_bytes()).json()
        stored = next(routes.NOTE_ATTACHMENTS_DIR.glob("note_*.pdf"))

        removed_pdf = client.delete(f"/api/notes/{uploaded['id']}/pdf")
        assert removed_pdf.status_code == 200
        assert not stored.exists()
        assert unrelated.read_bytes() == b"leave untouched"
        assert client.get("/api/notes").json()[0]["pdf_filename"] is None

        second = _upload_note(client, content=pdf_path.read_bytes()).json()
        second_path = next(routes.NOTE_ATTACHMENTS_DIR.glob("note_*.pdf"))
        deleted_note = client.delete(f"/api/notes/{second['id']}")
        assert deleted_note.status_code == 200
        assert not second_path.exists()
        assert unrelated.read_bytes() == b"leave untouched"


def test_legacy_notes_table_migrates_pdf_metadata_columns_without_data_loss(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE notes (id INTEGER PRIMARY KEY, user_id INTEGER, title VARCHAR(255) NOT NULL, "
            "content TEXT NOT NULL, subject VARCHAR(100), created_at DATETIME)"
        ))
        connection.execute(text(
            "INSERT INTO notes (id, user_id, title, content) VALUES (1, 1, 'Keep', 'Existing note')"
        ))
    monkeypatch.setattr("app.database.database.engine", engine)

    from app.database.database import create_tables

    create_tables()

    columns = {column["name"] for column in inspect(engine).get_columns("notes")}
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT title, content, pdf_filename, pdf_storage_name FROM notes WHERE id = 1"
        )).one()
    assert {"pdf_filename", "pdf_storage_name"} <= columns
    assert row == ("Keep", "Existing note", None, None)