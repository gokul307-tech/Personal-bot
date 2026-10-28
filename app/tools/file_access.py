import os
import re
from pathlib import Path

from app.api.auth_context import current_user_id
from app.config.settings import documents_dir_for_user


_USER_DIRECTORY = re.compile(r"user_\d+", re.IGNORECASE)


def resolve_user_document_path(file_path: str) -> Path:
    if not isinstance(file_path, str) or not file_path.strip():
        raise PermissionError("File access is restricted to your documents.")

    user_id = current_user_id()
    user_root = documents_dir_for_user(user_id)
    root = user_root.resolve()
    if user_id != 1 and os.path.normcase(str(root)) != os.path.normcase(str(user_root.absolute())):
        raise PermissionError("File access is restricted to your documents.")

    requested_path = Path(file_path)
    candidate = requested_path if requested_path.is_absolute() else root / requested_path

    try:
        path = candidate.resolve(strict=True)
    except FileNotFoundError:
        raise
    except (OSError, RuntimeError) as exc:
        raise PermissionError("File access is restricted to your documents.") from exc

    try:
        relative_path = path.relative_to(root)
    except ValueError as exc:
        raise PermissionError("File access is restricted to your documents.") from exc

    if user_id == 1 and any(_USER_DIRECTORY.fullmatch(part) for part in relative_path.parts):
        raise PermissionError("File access is restricted to your documents.")

    if not path.is_file():
        raise ValueError("Path is not a file.")

    return path
