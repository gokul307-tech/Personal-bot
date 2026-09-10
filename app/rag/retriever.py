from app.rag.vector_store import search
from app.tools.embeddings import create_embedding


def retrieve(
    query: str,
    top_k: int = 5,
    minimum_score: float = 0.25,
) -> list[dict]:

    if not query.strip():
        return []

    query_embedding = create_embedding(query)

    results = search(
        query_embedding=query_embedding,
        top_k=top_k,
    )

    return [
        result
        for result in results
        if result.get("score", 0.0)
        >= minimum_score
    ]