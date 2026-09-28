import json
import math
from pathlib import Path
from typing import Any

from app.config.settings import VECTOR_STORE_DIR


STORE_FILE = VECTOR_STORE_DIR / "vectors.json"


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
            return data

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

    temporary_file = STORE_FILE.with_suffix(".tmp")

    with temporary_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            documents,
            file,
            ensure_ascii=False,
        )

    temporary_file.replace(STORE_FILE)


def add_documents(
    documents: list[dict[str, Any]],
) -> int:

    if not documents:
        return 0

    store = _load_store()

    store.extend(documents)

    _save_store(store)

    return len(documents)


def clear_store() -> None:
    _save_store([])


def get_all_documents() -> list[dict[str, Any]]:
    return _load_store()


def delete_documents_by_filename(filename: str) -> int:
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

    if len(first) != len(second):
        return 0.0

    dot = sum(
        a * b
        for a, b in zip(first, second)
    )

    first_norm = math.sqrt(
        sum(a * a for a in first)
    )

    second_norm = math.sqrt(
        sum(b * b for b in second)
    )

    if first_norm == 0 or second_norm == 0:
        return 0.0

    return dot / (
        first_norm * second_norm
    )


def search(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:

    documents = _load_store()

    scored = []

    for document in documents:

        embedding = document.get("embedding")

        if not embedding:
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