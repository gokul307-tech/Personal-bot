from pathlib import Path

from app.config.settings import DOCUMENTS_DIR
from app.tools.rag import ingest_document


def list_documents() -> list[str]:

    if not DOCUMENTS_DIR.exists():
        return []

    return [
        path.name
        for path in DOCUMENTS_DIR.iterdir()
        if path.is_file()
    ]


def ingest_document_by_name(
    filename: str,
) -> dict:

    if not filename or Path(filename).name != filename:
        return {
            "success": False,
            "error": "Invalid document name.",
        }

    path = (
        DOCUMENTS_DIR / filename
    ).resolve()

    try:
        path.relative_to(
            DOCUMENTS_DIR.resolve()
        )

    except ValueError:

        return {
            "success": False,
            "error": "Invalid document path.",
        }

    if not path.is_file():
        return {
            "success": False,
            "error": "Document does not exist.",
        }

    return ingest_document(
        str(path)
    )