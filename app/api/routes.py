from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.agent.agent import VDSSAgent
from app.api.dependencies import get_agent
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationRename,
    HealthResponse,
    MemoryCreate,
    NoteCreate,
    NoteUpdate,
    StudyPlanCreate,
    StudyPlanUpdate,
)
from app.config.settings import APP_NAME, DOCUMENTS_DIR
from app.database import crud
from app.database.database import get_db
from app.database.models import StudyPlan
from app.tools.rag import ingest_document
from app.rag.vector_store import delete_documents_by_filename, get_all_documents


router = APIRouter()
USER_ID = 1


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
        crud.add_message(db, conversation.id, "user", request.message)
        context = [
            {"role": item.role, "content": item.content}
            for item in crud.get_messages(db, conversation.id)[-20:]
        ]
        response = agent.run(
            user_message=request.message,
            db=db,
            conversation_messages=context,
        )
        crud.add_message(db, conversation.id, "assistant", response)
        if conversation.title == "New Chat":
            conversation.title = request.message.strip().splitlines()[0][:60]
            db.commit()
        return {"response": response, "conversation_id": conversation.id}
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
                "preview": messages[-1].content[:100] if messages else "Start a new study session",
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
        if not crud.delete_conversation(db, conversation_id, USER_ID):
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"deleted": True}
    finally:
        db.close()


@router.delete("/conversations")
def remove_all_conversations():
    db = next(get_db())
    try:
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
            notes = [note for note in notes if query in note.title.casefold() or query in note.content.casefold()]
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
        return [{"id": plan.id, "title": plan.title, "subject": plan.subject, "description": plan.description, "scheduled_at": plan.scheduled_at, "completed": plan.completed} for plan in crud.get_study_plans(db, USER_ID)]
    finally:
        db.close()


@router.post("/study-plans")
def create_study_plan(request: StudyPlanCreate):
    db = next(get_db())
    try:
        scheduled_at = datetime.fromisoformat(request.scheduled_at) if request.scheduled_at else None
        plan = crud.create_study_plan(db, request.title, request.subject, request.description, scheduled_at, USER_ID)
        return {"id": plan.id, "title": plan.title, "subject": plan.subject, "description": plan.description, "scheduled_at": plan.scheduled_at, "completed": plan.completed}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="scheduled_at must be an ISO datetime") from exc
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
        return {"id": plan.id, "title": plan.title, "subject": plan.subject, "description": plan.description, "scheduled_at": plan.scheduled_at, "completed": plan.completed}
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
    for path in DOCUMENTS_DIR.iterdir():
        if not path.is_file() or (q and q.casefold() not in path.name.casefold()):
            continue
        documents.append({
            "filename": path.name,
            "size": path.stat().st_size,
            "file_type": path.suffix.lower().lstrip("."),
            "uploaded_at": datetime.fromtimestamp(path.stat().st_mtime),
            "status": "processed" if path.name in indexed else "uploaded",
        })
    return documents


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
    target.write_bytes(content)
    delete_documents_by_filename(safe_name)
    ingestion = ingest_document(str(target))
    return {"filename": safe_name, "status": "processed" if ingestion.get("success") else "uploaded", "ingestion": ingestion}


@router.delete("/documents/{filename}")
def remove_document(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid document name")
    target = DOCUMENTS_DIR / safe_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Document not found")
    target.unlink()
    delete_documents_by_filename(safe_name)
    return {"deleted": True, "filename": safe_name}
