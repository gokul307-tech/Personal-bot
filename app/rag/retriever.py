import math

from app.rag.vector_store import search
from app.tools.embeddings import create_embedding


def retrieve(
    query: str,
    top_k: int = 5,
    minimum_score: float = 0.25,
    filename: str | None = None,
) -> list[dict]:

    if (
        not isinstance(query, str)
        or not query.strip()
        or isinstance(top_k, bool)
        or not isinstance(top_k, int)
        or top_k <= 0
    ):
        return []
    if (
        isinstance(minimum_score, bool)
        or not isinstance(minimum_score, (int, float))
        or not math.isfinite(minimum_score)
        or not 0 <= minimum_score <= 1
    ):
        raise ValueError("minimum_score must be between 0 and 1.")

    query_embedding = create_embedding(query)

    results = search(
        query_embedding=query_embedding,
        top_k=top_k,
        filename=filename,
    )

    return [
        result
        for result in results
        if result.get("score", 0.0)
        >= minimum_score
    ]