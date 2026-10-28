from pathlib import Path
import logging
from uuid import uuid4

from app.api.auth_context import current_user_id
from app.config.settings import CHUNK_OVERLAP, CHUNK_SIZE
from app.rag.chunker import chunk_document_pages
from app.rag.document_loader import load_document_pages
from app.rag.retriever import retrieve
from app.rag.vector_store import add_documents, delete_documents_by_filename, get_all_documents
from app.tools.embeddings import create_embeddings
from app.tools.file_access import resolve_user_document_path


logger = logging.getLogger(__name__)


def ingest_document(
    file_path: str,
    *,
    private: bool = False,
    owner_id: int | None = None,
) -> dict:

    owner_id = current_user_id() if owner_id is None else owner_id
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
                    "owner_id": owner_id,
                    "page_number": chunk["page_number"],
                }
            )

        previous_documents = [
            item for item in get_all_documents(owner_id)
            if item.get("filename") == path.name
        ]
        delete_documents_by_filename(path.name, owner_id)
        try:
            count = add_documents(documents)
        except Exception:
            if previous_documents:
                add_documents(previous_documents)
            raise
        if count != len(documents):
            delete_documents_by_filename(path.name, owner_id)
            if previous_documents:
                add_documents(previous_documents)
            raise RuntimeError("Vector-store count did not match document chunks.")

        return {
            "success": True,
            "filename": path.name,
            "chunks_added": count,
            "pages_processed": len(pages),
        }

    except Exception as exc:
        logger.exception("Document ingestion failed for %s", path.name)
        error = str(exc) if isinstance(exc, (ValueError, PermissionError, FileNotFoundError)) else "Document indexing failed. Please try again."
        return {
            "success": False,
            "error": error,
        }


def ingest_project_document(
    filename: str,
) -> dict:
    try:
        path = resolve_user_document_path(filename)
    except FileNotFoundError:
        return {"success": False, "error": "Document does not exist."}
    except (PermissionError, ValueError):
        return {"success": False, "error": "Document access is restricted to your documents."}
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
        owner_id=current_user_id(),
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