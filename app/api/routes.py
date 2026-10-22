from datetime import date, datetime
import json
import logging
import mimetypes
from pathlib import Path
from uuid import uuid4
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.agent.agent import VDSSAgent
from app.api.dependencies import get_agent
from app.api.schemas import (
    ChatRequest,
    ChatPreferences,
    ChatResponse,
    ConversationCreate,
    ConversationRename,
    HealthResponse,
    MemoryCreate,
    NoteCreate,
    NoteUpdate,
    StudyPlanCreate,
    StudyPlanBulkCreate,
    StudyPlanRequest,
    StudyPlanUpdate,
)
from app.config.settings import APP_NAME, DOCUMENTS_DIR, UPLOADS_DIR
from app.database import crud
from app.database.database import get_db
from app.database.models import Note, StudyPlan
from app.tools.pdf_reader import read_pdf_pages
from app.tools.rag import ingest_document
from app.rag.vector_store import add_documents, delete_documents_by_filename, get_all_documents
from app.services.study_plan_service import categorize_study_plans, generate_study_schedule


router = APIRouter()
logger = logging.getLogger(__name__)
USER_ID = 1
CHAT_ATTACHMENTS_DIR = UPLOADS_DIR / "chat-attachments"
NOTE_ATTACHMENTS_DIR = UPLOADS_DIR / "note-attachments"
ATTACHMENT_MARKER = "\n\n<!--sage-attachments:"


def _message_attachments(content: str) -> list[dict]:
    marker_index = content.rfind(ATTACHMENT_MARKER)
    if marker_index < 0 or not content.endswith("-->"):
        return []
    try:
        attachments = json.loads(content[marker_index + len(ATTACHMENT_MARKER):-3])
    except json.JSONDecodeError:
        return []
    return attachments if isinstance(attachments, list) else []


def _message_text(content: str) -> str:
    marker_index = content.rfind(ATTACHMENT_MARKER)
    return content[:marker_index] if marker_index >= 0 else content


def _note_pdf_path(note: Note) -> Path | None:
    if not note.pdf_storage_name:
        return None
    storage_name = note.pdf_storage_name
    if Path(storage_name).name != storage_name or not storage_name.endswith(".pdf"):
        raise HTTPException(status_code=500, detail="Stored note PDF reference is invalid")
    root = NOTE_ATTACHMENTS_DIR.resolve()
    path = (root / storage_name).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Stored note PDF reference is invalid") from exc
    return path


def _stage_note_pdf(note: Note) -> tuple[Path | None, Path | None]:
    path = _note_pdf_path(note)
    if path is None or not path.exists():
        return path, None
    staged = path.with_name(f".{path.name}.{uuid4().hex}.deleting")
    path.replace(staged)
    return path, staged


def _restore_staged_note_pdf(original: Path | None, staged: Path | None) -> None:
    if original is not None and staged is not None and staged.exists():
        staged.replace(original)


def _serialize_note(note: Note) -> dict:
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content,
        "subject": note.subject,
        "created_at": note.created_at,
        "pdf_filename": note.pdf_filename,
        "has_pdf": bool(note.pdf_storage_name),
    }


def _delete_conversation_attachments(conversation_id: int, db) -> None:
    folder = CHAT_ATTACHMENTS_DIR / str(conversation_id)
    if not folder.exists():
        return
    for message in crud.get_messages(db, conversation_id):
        for attachment in _message_attachments(message.content):
            filename = Path(str(attachment.get("source", ""))).name
            if not filename:
                continue
            delete_documents_by_filename(filename)
            (folder / filename).unlink(missing_ok=True)
    shutil.rmtree(folder, ignore_errors=True)


@router.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok", "application": APP_NAME}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, agent: VDSSAgent = Depends(get_agent)):
    db = next(get_db())
    try:
        conversation = (
            crud.get_conversation(db, request.conversation_id, USER_ID)
            if request.conversation_id
            else crud.create_conversation(db, USER_ID)
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if request.source_filename:
            safe_filename = Path(request.source_filename).name
            library_path = DOCUMENTS_DIR / safe_filename
            attachment_path = CHAT_ATTACHMENTS_DIR / str(conversation.id) / safe_filename
            if safe_filename != request.source_filename or not (library_path.is_file() or attachment_path.is_file()):
                raise HTTPException(status_code=404, detail="Selected document not found")
        crud.add_message(db, conversation.id, "user", request.message)
        stored_messages = crud.get_messages(db, conversation.id)
        if not request.source_filename:
            if request.keep_attachment_context:
                for item in reversed(stored_messages[:-1]):
                    attachments = _message_attachments(item.content)
                    if attachments:
                        request.source_filename = attachments[-1].get("source")
                        break
        context = [
            {"role": item.role, "content": _message_text(item.content)}
            for item in stored_messages[-20:]
        ]
        try:
            response = agent.run(
                user_message=request.message,
                db=db,
                conversation_messages=context,
                source_filename=request.source_filename,
                preferences=request.preferences.model_dump(),
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("SAGE agent failed for conversation %s", conversation.id)
            raise HTTPException(
                status_code=503,
                detail="SAGE could not complete that request. Please try again.",
            ) from exc
        if not isinstance(response, str) or not response.strip():
            raise HTTPException(
                status_code=503,
                detail="SAGE returned an empty response. Please try again.",
            )
        crud.add_message(db, conversation.id, "assistant", response)
        if request.auto_title and conversation.title == "New Chat":
            conversation.title = request.message.strip().splitlines()[0][:60]
            db.commit()
        return {"response": response, "conversation_id": conversation.id}
    finally:
        db.close()


@router.post("/chat/attachments", response_model=ChatResponse)
async def chat_with_attachment(
    message: str = Form(..., min_length=1, max_length=20_000),
    conversation_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    preferences: str = Form(default="{}"),
    auto_title: bool = Form(default=True),
    agent: VDSSAgent = Depends(get_agent),
):
    try:
        chat_preferences = ChatPreferences.model_validate_json(preferences)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid chat preferences") from exc

    db = next(get_db())
    stored_path: Path | None = None
    source_filename: str | None = None
    message_saved = False
    try:
        conversation = (
            crud.get_conversation(db, conversation_id, USER_ID)
            if conversation_id
            else crud.create_conversation(db, USER_ID)
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        display_name = Path(file.filename or "").name
        extension = Path(display_name).suffix.lower()
        if not display_name or extension not in {".txt", ".md", ".pdf", ".docx", ".csv", ".py"}:
            raise HTTPException(status_code=400, detail="Unsupported document type")
        content = await file.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Document is too large")

        source_filename = f"attachment_{uuid4().hex}{extension}"
        folder = CHAT_ATTACHMENTS_DIR / str(conversation.id)
        folder.mkdir(parents=True, exist_ok=True)
        stored_path = folder / source_filename
        stored_path.write_bytes(content)
        ingestion = ingest_document(str(stored_path), private=True)
        if not ingestion.get("success"):
            delete_documents_by_filename(source_filename)
            stored_path.unlink(missing_ok=True)
            detail = ingestion.get("error")
            if not isinstance(detail, str) or not detail.strip():
                detail = "Could not process this attachment"
            raise HTTPException(status_code=422, detail=detail)

        attachment = {
            "filename": display_name,
            "file_type": extension.lstrip("."),
            "size": len(content),
            "source": source_filename,
        }
        marker = ATTACHMENT_MARKER + json.dumps([attachment], ensure_ascii=True) + "-->"
        crud.add_message(db, conversation.id, "user", message + marker)
        message_saved = True
        context = [
            {"role": item.role, "content": _message_text(item.content)}
            for item in crud.get_messages(db, conversation.id)[-20:]
        ]
        try:
            response = agent.run(
                user_message=message,
                db=db,
                conversation_messages=context,
                source_filename=source_filename,
                preferences=chat_preferences.model_dump(),
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("SAGE attachment response failed for conversation %s", conversation.id)
            raise HTTPException(
                status_code=503,
                detail="SAGE could not complete that request. Please try again.",
            ) from exc
        if not isinstance(response, str) or not response.strip():
            raise HTTPException(
                status_code=503,
                detail="SAGE returned an empty response. Please try again.",
            )
        crud.add_message(db, conversation.id, "assistant", response)
        if auto_title and conversation.title == "New Chat":
            conversation.title = message.strip().splitlines()[0][:60]
            db.commit()
        return {"response": response, "conversation_id": conversation.id}
    except Exception:
        if source_filename and not message_saved:
            delete_documents_by_filename(source_filename)
        if stored_path and not message_saved:
            stored_path.unlink(missing_ok=True)
        raise
    finally:
        db.close()


@router.get("/conversations")
def list_conversations():
    db = next(get_db())
    try:
        result = []
        for item in crud.get_conversations(db, USER_ID):
            messages = crud.get_messages(db, item.id)
            result.append({
                "id": item.id,
                "title": item.title,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "preview": _message_text(messages[-1].content)[:100] if messages else "Start a new study session",
            })
        return result
    finally:
        db.close()


@router.post("/conversations")
def create_conversation(request: ConversationCreate):
    db = next(get_db())
    try:
        item = crud.create_conversation(db, USER_ID, request.title.strip() or "New Chat")
        return {"id": item.id, "title": item.title, "created_at": item.created_at, "updated_at": item.updated_at}
    finally:
        db.close()


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int):
    db = next(get_db())
    try:
        item = crud.get_conversation(db, conversation_id, USER_ID)
        if item is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {
            "id": item.id,
            "title": item.title,
            "messages": [
                {"id": message.id, "role": message.role, "content": message.content, "created_at": message.created_at}
                for message in crud.get_messages(db, conversation_id)
            ],
        }
    finally:
        db.close()


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: int, request: ConversationRename):
    db = next(get_db())
    try:
        item = crud.get_conversation(db, conversation_id, USER_ID)
        if item is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        item.title = request.title.strip()
        db.commit()
        return {"id": item.id, "title": item.title}
    finally:
        db.close()


@router.delete("/conversations/{conversation_id}")
def remove_conversation(conversation_id: int):
    db = next(get_db())
    try:
        _delete_conversation_attachments(conversation_id, db)
        if not crud.delete_conversation(db, conversation_id, USER_ID):
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"deleted": True}
    finally:
        db.close()


@router.delete("/conversations")
def remove_all_conversations():
    db = next(get_db())
    try:
        for conversation in crud.get_conversations(db, USER_ID):
            _delete_conversation_attachments(conversation.id, db)
        return {"deleted": crud.delete_all_conversations(db, USER_ID)}
    finally:
        db.close()


@router.get("/notes")
def list_notes(q: str | None = None):
    db = next(get_db())
    try:
        notes = crud.get_notes(db, user_id=USER_ID)
        if q:
            query = q.casefold()
            notes = [note for note in notes if query in note.title.casefold() or query in note.content.casefold() or query in (note.subject or "").casefold()]
        return [{"id": note.id, "title": note.title, "content": note.content, "subject": note.subject, "created_at": note.created_at} for note in notes]
    finally:
        db.close()


@router.post("/notes")
def create_note(request: NoteCreate):
    db = next(get_db())
    try:
        note = crud.create_note(db, request.title, request.content, request.subject, USER_ID)
        return {"id": note.id, "title": note.title, "content": note.content, "subject": note.subject, "created_at": note.created_at}
    finally:
        db.close()


@router.patch("/notes/{note_id}")
def update_note(note_id: int, request: NoteUpdate):
    db = next(get_db())
    try:
        note = crud.get_note(db, note_id, USER_ID)
        if note is None:
            raise HTTPException(status_code=404, detail="Note not found")
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(note, field, value)
        db.commit()
        db.refresh(note)
        return {"id": note.id, "title": note.title, "content": note.content, "subject": note.subject}
    finally:
        db.close()


@router.delete("/notes/{note_id}")
def remove_note(note_id: int):
    db = next(get_db())
    try:
        if not crud.delete_note(db, note_id, USER_ID):
            raise HTTPException(status_code=404, detail="Note not found")
        return {"deleted": True}
    finally:
        db.close()


@router.get("/study-plans")
def list_study_plans():
    db = next(get_db())
    try:
        return [_serialize_study_plan(plan) for plan in crud.get_study_plans(db, USER_ID)]
    finally:
        db.close()


def _serialize_study_plan(plan: StudyPlan) -> dict:
    return {
        "id": plan.id,
        "title": plan.title,
        "subject": plan.subject,
        "description": plan.description,
        "scheduled_at": plan.scheduled_at,
        "completed": plan.completed,
        "priority": plan.priority,
        "estimated_minutes": plan.estimated_minutes,
    }


def _save_study_plan_tasks(db, tasks: list[dict]) -> tuple[list[StudyPlan], int]:
    existing = crud.get_study_plans(db, USER_ID)

    def signature(title: str, subject: str | None, scheduled_at: datetime | None) -> tuple[str, str, str | None]:
        return (
            title.strip().casefold(),
            (subject or "").strip().casefold(),
            scheduled_at.isoformat() if scheduled_at else None,
        )

    known = {
        signature(plan.title, plan.subject, plan.scheduled_at)
        for plan in existing
    }
    prepared = []
    duplicates = 0
    for task in tasks:
        scheduled_at = datetime.fromisoformat(task["scheduled_at"]) if task.get("scheduled_at") else None
        task_signature = signature(task["title"], task.get("subject"), scheduled_at)
        if task_signature in known:
            duplicates += 1
            continue
        known.add(task_signature)
        prepared.append(StudyPlan(
            title=task["title"],
            subject=task.get("subject"),
            description=task.get("description"),
            scheduled_at=scheduled_at,
            user_id=USER_ID,
            priority=task.get("priority", "medium"),
            estimated_minutes=task.get("estimated_minutes", 60),
        ))
    try:
        db.add_all(prepared)
        db.flush()
        db.commit()
        for plan in prepared:
            db.refresh(plan)
    except Exception:
        db.rollback()
        raise
    return prepared, duplicates


@router.get("/study-plans/statistics")
def study_plan_statistics(today: date | None = None):
    db = next(get_db())
    try:
        plans = [_serialize_study_plan(plan) for plan in crud.get_study_plans(db, USER_ID)]
        return categorize_study_plans(plans, today or date.today())
    finally:
        db.close()


@router.post("/study-plans")
def create_study_plan(request: StudyPlanCreate):
    db = next(get_db())
    try:
        scheduled_at = datetime.fromisoformat(request.scheduled_at) if request.scheduled_at else None
        plan = crud.create_study_plan(
            db,
            request.title,
            request.subject,
            request.description,
            scheduled_at,
            USER_ID,
            request.priority,
            request.estimated_minutes,
        )
        return _serialize_study_plan(plan)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="scheduled_at must be an ISO datetime") from exc
    finally:
        db.close()


@router.post("/study-plans/from-request")
def create_study_plan_from_request(request: StudyPlanRequest):
    db = next(get_db())
    try:
        generated = generate_study_schedule(request.request, request.priority)
        plans, duplicates = _save_study_plan_tasks(db, generated)
        return {
            "tasks": [_serialize_study_plan(plan) for plan in plans],
            "created": len(plans),
            "duplicates": duplicates,
        }
    finally:
        db.close()


@router.post("/study-plans/preview")
def preview_study_plan(request: StudyPlanRequest):
    return {"tasks": generate_study_schedule(request.request, request.priority)}


@router.post("/study-plans/bulk")
def create_study_plan_tasks(request: StudyPlanBulkCreate):
    db = next(get_db())
    try:
        plans, duplicates = _save_study_plan_tasks(
            db,
            [task.model_dump() for task in request.tasks],
        )
        return {
            "tasks": [_serialize_study_plan(plan) for plan in plans],
            "created": len(plans),
            "duplicates": duplicates,
        }
    finally:
        db.close()


@router.patch("/study-plans/{plan_id}")
def update_study_plan(
    plan_id: int,
    request: StudyPlanUpdate | None = None,
    completed: bool | None = None,
):
    db = next(get_db())
    try:
        plan = db.get(StudyPlan, plan_id)
        if plan is None or plan.user_id != USER_ID:
            raise HTTPException(status_code=404, detail="Study plan not found")
        updates = request.model_dump(exclude_unset=True) if request else {}
        if completed is not None:
            updates["completed"] = completed
        if "scheduled_at" in updates:
            try:
                updates["scheduled_at"] = datetime.fromisoformat(updates["scheduled_at"]) if updates["scheduled_at"] else None
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="scheduled_at must be an ISO datetime") from exc
        for field, value in updates.items():
            setattr(plan, field, value)
        db.commit()
        db.refresh(plan)
        return _serialize_study_plan(plan)
    finally:
        db.close()


@router.delete("/study-plans/{plan_id}")
def delete_study_plan(plan_id: int):
    db = next(get_db())
    try:
        plan = db.get(StudyPlan, plan_id)
        if plan is None or plan.user_id != USER_ID:
            raise HTTPException(status_code=404, detail="Study plan not found")
        db.delete(plan)
        db.commit()
        return {"deleted": True}
    finally:
        db.close()


@router.get("/memories")
def list_memories(q: str | None = None):
    db = next(get_db())
    try:
        memories = crud.get_memories(db, user_id=USER_ID)
        if q:
            query = q.casefold()
            memories = [item for item in memories if query in item.content.casefold()]
        return [{"id": item.id, "content": item.content, "memory_type": item.memory_type, "importance": item.importance, "created_at": item.created_at} for item in memories]
    finally:
        db.close()


@router.post("/memories")
def create_memory(request: MemoryCreate):
    db = next(get_db())
    try:
        item = crud.create_memory(db, request.content, request.memory_type, request.importance, USER_ID)
        return {"id": item.id, "content": item.content, "memory_type": item.memory_type, "importance": item.importance, "created_at": item.created_at}
    finally:
        db.close()


@router.delete("/memories/{memory_id}")
def remove_memory(memory_id: int):
    db = next(get_db())
    try:
        if not crud.delete_memory(db, memory_id, USER_ID):
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"deleted": True}
    finally:
        db.close()


@router.get("/documents")
def list_documents(q: str | None = None):
    indexed = {item.get("filename") for item in get_all_documents()}
    documents = []
    if DOCUMENTS_DIR.exists():
        for path in DOCUMENTS_DIR.iterdir():
            if not path.is_file() or path.name.startswith(".") or (q and q.casefold() not in path.name.casefold()):
                continue
            documents.append({
                "filename": path.name,
                "size": path.stat().st_size,
                "file_type": path.suffix.lower().lstrip("."),
                "uploaded_at": datetime.fromtimestamp(path.stat().st_mtime),
                "status": "ready" if path.name in indexed else "failed",
                "storage_type": "library",
            })

    db = next(get_db())
    try:
        seen = set()
        for conversation in crud.get_conversations(db, USER_ID):
            folder = CHAT_ATTACHMENTS_DIR / str(conversation.id)
            for message in crud.get_messages(db, conversation.id):
                for attachment in _message_attachments(message.content):
                    source = str(attachment.get("source", ""))
                    if not source or Path(source).name != source or (conversation.id, source) in seen:
                        continue
                    seen.add((conversation.id, source))
                    if q and q.casefold() not in str(attachment.get("filename", source)).casefold():
                        continue
                    path = folder / source
                    exists = path.is_file()
                    documents.append({
                        "filename": str(attachment.get("filename") or source),
                        "size": path.stat().st_size if exists else max(0, int(attachment.get("size", 0) or 0)),
                        "file_type": str(attachment.get("file_type") or Path(source).suffix.lstrip(".")).lower(),
                        "uploaded_at": message.created_at,
                        "status": "missing" if not exists else "ready" if source in indexed else "failed",
                        "storage_type": "attachment",
                        "source": source,
                        "conversation_id": conversation.id,
                        "delete_url": f"/api/documents/attachments/{conversation.id}/{source}",
                    })
        return sorted(documents, key=lambda item: item["uploaded_at"], reverse=True)
    finally:
        db.close()


@router.get("/documents/{filename}/open")
def open_document(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid document name")
    target = DOCUMENTS_DIR / safe_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Document not found")
    media_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type)


@router.post("/documents")
def upload_document(file: UploadFile = File(...)):
    safe_name = Path(file.filename or "").name
    allowed_extensions = {".txt", ".md", ".pdf", ".docx", ".csv", ".py"}
    if not safe_name or Path(safe_name).suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Unsupported document type")
    max_bytes = 10 * 1024 * 1024
    content = file.file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="Document is too large")
    target = DOCUMENTS_DIR / safe_name
    previous_content = target.read_bytes() if target.exists() else None
    previous_documents = [item for item in get_all_documents() if item.get("filename") == safe_name]
    temporary = DOCUMENTS_DIR / f".{uuid4().hex}{target.suffix}"
    try:
        temporary.write_bytes(content)
        temporary.replace(target)
        delete_documents_by_filename(safe_name)
        ingestion = ingest_document(str(target))
        if not ingestion.get("success"):
            detail = ingestion.get("error")
            if not isinstance(detail, str) or not detail.strip():
                detail = "Could not process this document"
            raise HTTPException(status_code=422, detail=detail)
    except Exception:
        if previous_content is None:
            target.unlink(missing_ok=True)
        else:
            restore = DOCUMENTS_DIR / f".{uuid4().hex}{target.suffix}"
            restore.write_bytes(previous_content)
            restore.replace(target)
        delete_documents_by_filename(safe_name)
        if previous_documents:
            add_documents(previous_documents)
        raise
    finally:
        temporary.unlink(missing_ok=True)
    return {"filename": safe_name, "status": "ready", "ingestion": ingestion}


@router.delete("/documents/{filename}")
def remove_document(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid document name")
    target = DOCUMENTS_DIR / safe_name
    if target.is_file():
        target.unlink()
        delete_documents_by_filename(safe_name)
        return {"deleted": True, "filename": safe_name}

    db = next(get_db())
    try:
        matches = {}
        for conversation in crud.get_conversations(db, USER_ID):
            for message in crud.get_messages(db, conversation.id):
                for attachment in _message_attachments(message.content):
                    if attachment.get("filename") == safe_name:
                        source = str(attachment.get("source", ""))
                        if source and Path(source).name == source:
                            matches[(conversation.id, source)] = source
        if len(matches) > 1:
            raise HTTPException(
                status_code=409,
                detail="Multiple chat attachments have this name. Refresh Uploads and delete the specific entry.",
            )
        if matches:
            conversation_id, source = next(iter(matches))
            _delete_chat_attachment(conversation_id, source, db)
        else:
            delete_documents_by_filename(safe_name)
        return {"deleted": True, "filename": safe_name}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _delete_chat_attachment(conversation_id: int, source: str, db) -> None:
    safe_source = Path(source).name
    if not safe_source or safe_source != source:
        raise HTTPException(status_code=400, detail="Invalid attachment name")

    conversation = crud.get_conversation(db, conversation_id, USER_ID)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    matching_messages = []
    for message in crud.get_messages(db, conversation_id):
        attachments = _message_attachments(message.content)
        if any(item.get("source") == safe_source for item in attachments):
            matching_messages.append((message, attachments))
    if not matching_messages:
        raise HTTPException(status_code=404, detail="Attachment not found")

    folder = (CHAT_ATTACHMENTS_DIR / str(conversation_id)).resolve()
    target = (folder / safe_source).resolve()
    try:
        target.relative_to(folder)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid attachment path") from exc

    target.unlink(missing_ok=True)
    delete_documents_by_filename(safe_source)
    for message, attachments in matching_messages:
        remaining = [item for item in attachments if item.get("source") != safe_source]
        text = _message_text(message.content)
        message.content = (
            text + ATTACHMENT_MARKER + json.dumps(remaining, ensure_ascii=True) + "-->"
            if remaining
            else text
        )
    db.commit()


@router.delete("/documents/attachments/{conversation_id}/{source}")
def remove_chat_attachment(conversation_id: int, source: str):
    db = next(get_db())
    try:
        _delete_chat_attachment(conversation_id, source, db)
        return {"deleted": True, "source": Path(source).name}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
