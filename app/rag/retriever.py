import math
import re

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

    page_match = re.search(r"\b(?:page|p\.)\s*(\d+)\b", query, re.IGNORECASE)
    page_number = int(page_match.group(1)) if page_match else None
    retrieval_query = re.sub(r"\b(?:page|p\.)\s*\d+\b", " ", query, flags=re.IGNORECASE).strip()

    query_embedding = []
    if retrieval_query:
        try:
            query_embedding = create_embedding(retrieval_query)
        except Exception:
            query_embedding = []

    results = search(
        query_embedding=query_embedding,
        top_k=top_k,
        filename=filename,
        query_text=retrieval_query,
        page_number=page_number,
    )

    return [
        result
        for result in results
        if result.get("score", 0.0)
        >= minimum_score
    ]