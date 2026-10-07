from functools import lru_cache

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
    return embeddings.tolist()


def create_embedding(
    text: str,
) -> list[float]:

    result = create_embeddings([text])

    return result[0]