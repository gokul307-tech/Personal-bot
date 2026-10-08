import json
import math
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from app.config.settings import VECTOR_STORE_DIR


STORE_FILE = VECTOR_STORE_DIR / "vectors.json"
_STORE_LOCK = RLock()


def _load_store() -> list[dict[str, Any]]:
    if not STORE_FILE.exists():
        return []

    try:
        with STORE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        return []

    except (json.JSONDecodeError, OSError):
        return []


def _save_store(
    documents: list[dict[str, Any]],
) -> None:

    VECTOR_STORE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = STORE_FILE.with_name(f"{STORE_FILE.name}.{uuid4().hex}.tmp")
    try:
        with temporary_file.open("w", encoding="utf-8") as file:
            json.dump(documents, file, ensure_ascii=False)
        temporary_file.replace(STORE_FILE)
    finally:
        temporary_file.unlink(missing_ok=True)


def add_documents(
    documents: list[dict[str, Any]],
) -> int:

    if not documents:
        return 0

    with _STORE_LOCK:
        store = _load_store()
        store.extend(documents)
        _save_store(store)

    return len(documents)


def clear_store() -> None:
    with _STORE_LOCK:
        _save_store([])


def get_all_documents() -> list[dict[str, Any]]:
    return _load_store()


def delete_documents_by_filename(filename: str) -> int:
    with _STORE_LOCK:
        store = _load_store()
        remaining = [item for item in store if item.get("filename") != filename]
        deleted = len(store) - len(remaining)
        if deleted:
            _save_store(remaining)
        return deleted


def cosine_similarity(
    first: list[float],
    second: list[float],
) -> float:

    if not first or not second:
        return 0.0

    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in first + second):
        return 0.0

    if len(first) != len(second):
        return 0.0

    first_scale = max(abs(value) for value in first)
    second_scale = max(abs(value) for value in second)
    if first_scale == 0 or second_scale == 0:
        return 0.0
    first_scaled = [value / first_scale for value in first]
    second_scaled = [value / second_scale for value in second]
    first_norm = math.sqrt(math.fsum(value * value for value in first_scaled))
    second_norm = math.sqrt(math.fsum(value * value for value in second_scaled))

    if first_norm == 0 or second_norm == 0:
        return 0.0

    similarity = math.fsum(
        (a / first_norm) * (b / second_norm)
        for a, b in zip(first_scaled, second_scaled)
    )
    return max(-1.0, min(1.0, similarity))


def search(
    query_embedding: list[float],
    top_k: int = 5,
    filename: str | None = None,
) -> list[dict[str, Any]]:

    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0 or not query_embedding:
        return []
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in query_embedding):
        return []

    documents = _load_store()

    scored = []

    for document in documents:

        if document.get("private") and not filename:
            continue

        if filename and document.get("filename") != filename:
            continue

        embedding = document.get("embedding")

        if not isinstance(embedding, list) or not embedding:
            continue
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in embedding):
            continue

        score = cosine_similarity(
            query_embedding,
            embedding,
        )

        item = dict(document)
        item["score"] = score

        scored.append(item)

    scored.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return scored[:top_k]