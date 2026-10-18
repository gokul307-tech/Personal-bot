from pathlib import Path
import logging
from uuid import uuid4

from app.config.settings import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DOCUMENTS_DIR,
)
from app.rag.chunker import chunk_document_pages
from app.rag.document_loader import load_document_pages
from app.rag.retriever import retrieve
from app.rag.vector_store import add_documents
from app.tools.embeddings import create_embeddings


logger = logging.getLogger(__name__)


def ingest_document(
    file_path: str,
    *,
    private: bool = False,
) -> dict:

    path = Path(file_path).resolve()

    if not path.exists():
        return {
            "success": False,
            "error": "Document does not exist.",
        }

    try:
        pages = load_document_pages(str(path))
        chunks = chunk_document_pages(
            pages,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )

        if not chunks:
            return {
                "success": False,
                "error": "No readable text found.",
            }

        embeddings = create_embeddings([chunk["text"] for chunk in chunks])
        if len(embeddings) != len(chunks):
            raise RuntimeError("Embedding count did not match document chunks.")

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
                    "text": chunk["text"],
                    "embedding": embedding,
                    "private": private,
                    "page_number": chunk["page_number"],
                }
            )

        count = add_documents(documents)
        if count != len(documents):
            raise RuntimeError("Vector-store count did not match document chunks.")

        return {
            "success": True,
            "filename": path.name,
            "chunks_added": count,
            "pages_processed": len(pages),
        }

    except Exception as exc:
        logger.exception("Document ingestion failed for %s", path.name)

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
    filename: str | None = None,
) -> list[dict]:

    results = retrieve(
        query=query,
        top_k=top_k,
        filename=filename,
    )

    return [
        {
            "source": result.get("source"),
            "filename": result.get("filename"),
            "chunk_index": result.get("chunk_index"),
            "page_number": result.get("page_number"),
            "score": round(
                float(result.get("score", 0)),
                4,
            ),
            "text": result.get("text", ""),
        }
        for result in results
    ]