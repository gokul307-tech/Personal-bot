from pathlib import Path
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree

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

    if path.suffix.lower() == ".docx":
        try:
            with ZipFile(path) as archive:
                document = ElementTree.fromstring(archive.read("word/document.xml"))
        except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise ValueError("Invalid DOCX document") from exc
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for paragraph in document.findall(".//w:p", namespace):
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
            if text:
                paragraphs.append(text)
        return "\n".join(paragraphs)

    if path.suffix.lower() in SUPPORTED_TEXT_EXTENSIONS:
        return read_file(str(path))

    raise ValueError(
        f"Unsupported document type: {path.suffix}"
    )