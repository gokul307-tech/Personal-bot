from pathlib import Path

from pypdf import PdfReader


def read_pdf(file_path: str) -> str:

    path = Path(file_path).resolve()

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

        return f"PDF reading error: {exc}"