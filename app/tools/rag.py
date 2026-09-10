from pathlib import Path
from uuid import uuid4

from app.config.settings import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DOCUMENTS_DIR,
)
from app.rag.chunker import chunk_text
from app.rag.document_loader import load_document
from app.rag.retriever import retrieve
from app.rag.vector_store import add_documents
from app.tools.embeddings import create_embeddings


def ingest_document(
    file_path: str,
) -> dict:

    path = Path(file_path).resolve()

    if not path.exists():
        return {
            "success": False,
            "error": "Document does not exist.",
        }

    try:
        text = load_document(str(path))

        chunks = chunk_text(
            text,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )

        if not chunks:
            return {
                "success": False,
                "error": "No readable text found.",
            }

        embeddings = create_embeddings(chunks)

        documents = []

        for index, (chunk, embedding) in enumerate(
            zip(chunks, embeddings)
        ):

            documents.append(
                {
                    "id": str(uuid4()),
                    "source": str(path),
                    "filename": path.name,
                    "chunk_index": index,
                    "text": chunk,
                    "embedding": embedding,
                }
            )

        count = add_documents(documents)

        return {
            "success": True,
            "filename": path.name,
            "chunks_added": count,
        }

    except Exception as exc:

        return {
            "success": False,
            "error": f"Document ingestion failed: {exc}",
        }


def ingest_project_document(
    filename: str,
) -> dict:

    path = DOCUMENTS_DIR / filename

    return ingest_document(str(path))


def search_knowledge(
    query: str,
    top_k: int = 5,
) -> list[dict]:

    results = retrieve(
        query=query,
        top_k=top_k,
    )

    return [
        {
            "source": result.get("source"),
            "filename": result.get("filename"),
            "chunk_index": result.get("chunk_index"),
            "score": round(
                float(result.get("score", 0)),
                4,
            ),
            "text": result.get("text", ""),
        }
        for result in results
    ]