import logging
from pathlib import Path

from pypdf import PdfReader

from app.config.settings import DATA_DIR
from app.tools.file_access import resolve_user_document_path


logger = logging.getLogger(__name__)


def read_pdf_pages(file_path: str) -> list[dict[str, str | int]]:
    path = Path(file_path).resolve()
    try:
        path.relative_to(DATA_DIR.resolve())
    except ValueError as exc:
        raise PermissionError("PDF access is restricted to the project data directory.") from exc

    if not path.exists():
        raise FileNotFoundError("PDF does not exist.")
    if not path.is_file():
        raise ValueError("PDF path is not a file.")
    if path.suffix.lower() != ".pdf":
        raise ValueError("File is not a PDF.")

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        logger.exception("PDF parsing failed for %s", path)
        raise ValueError("This PDF is malformed or unreadable.") from exc

    if reader.is_encrypted:
        raise ValueError("This PDF is password-protected. Remove the password and upload it again.")

    try:
        pages = [
            {"page_number": index + 1, "text": page.extract_text() or ""}
            for index, page in enumerate(reader.pages)
        ]
    except Exception as exc:
        logger.exception("PDF parsing failed for %s", path)
        raise ValueError("This PDF is malformed or unreadable.") from exc

    if not pages:
        raise ValueError("This PDF contains no pages.")
    if not any(page["text"].strip() for page in pages):
        raise ValueError("No selectable text was found. This PDF may be scanned; OCR is not available.")
    return pages


def read_pdf(file_path: str) -> str:
    path = resolve_user_document_path(file_path)
    pages = read_pdf_pages(str(path))
    result = "\n".join(
        f"\n--- Page {page['page_number']} ---\n{page['text']}"
        for page in pages
    )
    max_chars = 150_000
    if len(result) > max_chars:
        result = result[:max_chars] + "\n\n[PDF content truncated.]"
    return result


def read_pdf_from_data_dir(file_path: str) -> str:
    pages = read_pdf_pages(file_path)
    result = "\n".join(
        f"\n--- Page {page['page_number']} ---\n{page['text']}"
        for page in pages
    )
    max_chars = 150_000
    if len(result) > max_chars:
        result = result[:max_chars] + "\n\n[PDF content truncated.]"
    return result