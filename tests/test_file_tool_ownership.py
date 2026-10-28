import os
import subprocess

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.api.auth_context import reset_current_user_id, set_current_user_id
from app.agent.executor import ToolExecutor
from app.agent.registry import create_default_registry
from app.config import settings
from app.tools import notes as note_tools
from app.tools import rag as rag_tools
from app.tools.file_reader import read_file
from app.tools.pdf_reader import read_pdf
from app.tools.python_analysis import analyze_csv
from app.tools.rag import ingest_project_document, search_knowledge


OWNER_A = 17
OWNER_B = 29


def _as_user(user_id, callback, *args, **kwargs):
    token = set_current_user_id(user_id)
    try:
        return callback(*args, **kwargs)
    finally:
        reset_current_user_id(token)


def _write_text_pdf(path, text):
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


def _create_directory_link(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"Directory symlinks are unavailable: {exc}")

        def ps_quote(path):
            return "'" + str(path).replace("'", "''") + "'"

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"New-Item -ItemType Junction -Path {ps_quote(link)} "
                f"-Target {ps_quote(target)} -ErrorAction Stop | Out-Null",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"Directory links are unavailable: {result.stderr.strip()}")


def _remove_directory_link(link):
    if link.is_symlink():
        link.unlink()
    else:
        link.rmdir()


@pytest.fixture
def user_document_roots(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    documents_dir = data_dir / "documents"
    owner_a_dir = documents_dir / f"user_{OWNER_A}"
    owner_b_dir = documents_dir / f"user_{OWNER_B}"
    owner_a_dir.mkdir(parents=True)
    owner_b_dir.mkdir(parents=True)

    monkeypatch.setattr(settings, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr("app.tools.file_reader.DATA_DIR", data_dir)
    monkeypatch.setattr("app.tools.pdf_reader.DATA_DIR", data_dir)

    return owner_a_dir, owner_b_dir


@pytest.mark.parametrize(
    ("extension", "write_file", "tool", "unauthorized_result", "allowed_result"),
    [
        (
            ".txt",
            lambda path: path.write_text("owner B private notes", encoding="utf-8"),
            read_file,
            lambda result: isinstance(result, str) and result.startswith("Error:"),
            lambda result: result == "owner B private notes",
        ),
        (
            ".pdf",
            lambda path: _write_text_pdf(path, "owner B private notes"),
            read_pdf,
            lambda result: isinstance(result, PermissionError),
            lambda result: "owner B private notes" in result,
        ),
        (
            ".csv",
            lambda path: path.write_text("score\n91\n", encoding="utf-8"),
            analyze_csv,
            lambda result: result["success"] is False,
            lambda result: result["success"] is True and result["rows"] == 1,
        ),
    ],
)
def test_file_tools_restrict_other_users_and_allow_the_owner(
    user_document_roots,
    extension,
    write_file,
    tool,
    unauthorized_result,
    allowed_result,
):
    _owner_a_dir, owner_b_dir = user_document_roots
    private_file = owner_b_dir / f"private{extension}"
    write_file(private_file)

    try:
        result = _as_user(OWNER_A, tool, str(private_file))
    except PermissionError as exc:
        result = exc
    assert unauthorized_result(result)

    owned_result = _as_user(OWNER_B, tool, str(private_file))
    assert allowed_result(owned_result)


def test_file_reader_rejects_traversal_and_symlink_to_another_owner(
    user_document_roots,
):
    owner_a_dir, owner_b_dir = user_document_roots
    private_file = owner_b_dir / "private.txt"
    private_file.write_text("private", encoding="utf-8")

    traversal_result = _as_user(OWNER_A, read_file, "../user_29/private.txt")
    assert traversal_result.startswith("Error:")

    link = owner_a_dir / "other-user"
    _create_directory_link(link, owner_b_dir)

    try:
        symlink_result = _as_user(OWNER_A, read_file, str(link / private_file.name))
        assert symlink_result.startswith("Error:")
    finally:
        _remove_directory_link(link)


def test_user_root_link_cannot_redirect_to_another_owner(user_document_roots):
    owner_a_dir, owner_b_dir = user_document_roots
    (owner_b_dir / "private.txt").write_text("private", encoding="utf-8")
    original_owner_dir = owner_a_dir.with_name("user_17_original")
    owner_a_dir.rename(original_owner_dir)

    try:
        _create_directory_link(owner_a_dir, owner_b_dir)
        result = _as_user(OWNER_A, read_file, "private.txt")
        assert result.startswith("Error:")
    finally:
        if owner_a_dir.exists() or owner_a_dir.is_symlink():
            _remove_directory_link(owner_a_dir)
        original_owner_dir.rename(owner_a_dir)


def test_legacy_owner_cannot_read_user_subdirectories(user_document_roots):
    _owner_a_dir, owner_b_dir = user_document_roots
    private_file = owner_b_dir / "private.txt"
    private_file.write_text("private", encoding="utf-8")

    result = _as_user(1, read_file, str(private_file))

    assert result.startswith("Error:")


def test_document_ingestion_tool_rejects_traversal_and_search_owner_is_trusted(
    user_document_roots,
    monkeypatch,
):
    _owner_a_dir, owner_b_dir = user_document_roots
    private_file = owner_b_dir / "private.docx"
    private_file.write_bytes(b"not parsed")

    result = _as_user(OWNER_A, ingest_project_document, "../user_29/private.docx")

    assert result["success"] is False
    assert "restricted" in result["error"]

    calls = []
    owned_file = _owner_a_dir / "owned.txt"
    owned_file.write_text("owner A content", encoding="utf-8")
    monkeypatch.setattr(
        rag_tools,
        "ingest_document",
        lambda path: calls.append(path) or {"success": True},
    )
    assert _as_user(OWNER_A, ingest_project_document, "owned.txt") == {"success": True}
    assert calls == [str(owned_file.resolve())]

    calls.clear()
    monkeypatch.setattr(
        rag_tools,
        "retrieve",
        lambda **kwargs: calls.append(kwargs) or [],
    )
    _as_user(OWNER_A, search_knowledge, "private")

    assert calls == [{"query": "private", "top_k": 5, "filename": None, "owner_id": OWNER_A}]
    with pytest.raises(TypeError):
        _as_user(OWNER_A, search_knowledge, "private", owner_id=OWNER_B)


def test_database_tools_use_authenticated_owner_not_llm_owner_id(monkeypatch):
    registry = create_default_registry()
    owner_scoped_tools = (
        "add_note",
        "list_notes",
        "add_mark",
        "list_marks",
        "create_plan",
        "list_plans",
        "remember_information",
        "recall_information",
        "create_reminder_tool",
        "list_reminders",
        "create_event",
        "list_events",
    )
    for tool_name in owner_scoped_tools:
        properties = registry.get(tool_name)["parameters"]["properties"]
        assert "user_id" not in properties

    executor = ToolExecutor(registry)
    rejected = executor.execute("list_notes", {"db": object(), "user_id": OWNER_B})
    assert rejected == {
        "success": False,
        "error": "Invalid arguments for 'list_notes'.",
    }

    captured = {}
    monkeypatch.setattr(
        note_tools,
        "get_notes",
        lambda **kwargs: captured.update(kwargs) or [],
    )
    test_db = object()
    assert _as_user(OWNER_A, note_tools.list_notes, test_db) == []
    assert captured == {"db": test_db, "subject": None, "user_id": OWNER_A}
