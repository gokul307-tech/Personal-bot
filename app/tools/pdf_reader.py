import logging
from pathlib import Path

from pypdf import PdfReader

from app.config.settings import DATA_DIR


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

    reader = PdfReader(str(path))
    return [
        {"page_number": index + 1, "text": page.extract_text() or ""}
        for index, page in enumerate(reader.pages)
    ]


def read_pdf(file_path: str) -> str:

    path = Path(file_path).resolve()

    try:
        path.relative_to(DATA_DIR.resolve())
    except ValueError:
        return "Error: PDF access is restricted to the project data directory."

    if not path.exists():
        return "Error: PDF does not exist."

    if not path.is_file():
        return "Error: Path is not a file."

    if path.suffix.lower() != ".pdf":
        return "Error: File is not a PDF."

    try:

        reader = PdfReader(str(path))

        pages = []

        for index, page in enumerate(
            reader.pages
        ):

            text = page.extract_text() or ""

            pages.append(
                f"\n--- Page {index + 1} ---\n{text}"
            )

        result = "\n".join(pages)

        max_chars = 150_000

        if len(result) > max_chars:

            result = result[:max_chars]

            result += (
                "\n\n[PDF content truncated.]"
            )

        return result

    except Exception as exc:
        logger.exception("PDF reading failed for %s", path)
        return f"PDF reading error: {exc}"