from pathlib import Path

from app.config.settings import DATA_DIR


ALLOWED_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".py",
    ".js",
    ".html",
    ".css",
}


def read_file(file_path: str) -> str:

    path = Path(file_path).resolve()

    try:
        path.relative_to(DATA_DIR.resolve())
    except ValueError:
        return "Error: File access is restricted to the project data directory."

    if not path.exists():
        return "Error: File does not exist."

    if not path.is_file():
        return "Error: Path is not a file."

    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return (
            "Error: File type is not supported."
        )

    try:

        content = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        # Prevent enormous responses.
        max_chars = 100_000

        if len(content) > max_chars:

            content = content[:max_chars]

            content += (
                "\n\n[File truncated because it is "
                "too large.]"
            )

        return content

    except Exception as exc:

        return f"File reading error: {exc}"