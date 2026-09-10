from pathlib import Path

from app.tools.file_reader import read_file
from app.tools.pdf_reader import read_pdf


SUPPORTED_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".py",
    ".js",
    ".html",
    ".css",
}


def load_document(file_path: str) -> str:
    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    if path.suffix.lower() == ".pdf":
        return read_pdf(str(path))

    if path.suffix.lower() in SUPPORTED_TEXT_EXTENSIONS:
        return read_file(str(path))

    raise ValueError(
        f"Unsupported document type: {path.suffix}"
    )