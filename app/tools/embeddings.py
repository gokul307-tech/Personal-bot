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

    model = get_embedding_model()

    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
    )

    return embeddings.tolist()


def create_embedding(
    text: str,
) -> list[float]:

    result = create_embeddings([text])

    return result[0]