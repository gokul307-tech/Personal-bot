from functools import lru_cache
import math

from sentence_transformers import SentenceTransformer

from app.config.settings import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def get_embedding_model():
    return SentenceTransformer(EMBEDDING_MODEL)


def create_embeddings(
    texts: list[str],
) -> list[list[float]]:

    if not texts:
        return []
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("Embedding text cannot be blank.")

    model = get_embedding_model()

    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
    )

    if len(embeddings) != len(texts):
        raise RuntimeError("Embedding model returned an unexpected number of vectors.")
    vectors = embeddings.tolist()
    if not isinstance(vectors, list) or not vectors:
        raise RuntimeError("Embedding model returned no vectors.")
    dimensions = len(vectors[0]) if isinstance(vectors[0], list) else 0
    if not dimensions or any(not isinstance(vector, list) or len(vector) != dimensions for vector in vectors):
        raise RuntimeError("Embedding model returned inconsistent vector dimensions.")
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for vector in vectors for value in vector):
        raise RuntimeError("Embedding model returned non-finite vector values.")
    return vectors


def create_embedding(
    text: str,
) -> list[float]:

    result = create_embeddings([text])

    return result[0]