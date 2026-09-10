from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_agent
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ConversationCreate,
    ConversationRename,
)
from app.config.settings import APP_NAME
from app.database.database import get_db
from app.database import crud
from app.agent.agent import VDSSAgent


router = APIRouter()
USER_ID = 1


@router.get(
    "/health",
    response_model=HealthResponse,
)
def health():

    return {
        "status": "ok",
        "application": APP_NAME,
    }


@router.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
    agent: VDSSAgent = Depends(get_agent),
):

    db_generator = get_db()

    db = next(db_generator)

    try:

        conversation = crud.get_conversation(db, request.conversation_id, USER_ID) if request.conversation_id else crud.create_conversation(db, USER_ID)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        crud.add_message(db, conversation.id, "user", request.message)
        response = agent.run(
            user_message=request.message,
            db=db,
        )
        crud.add_message(db, conversation.id, "assistant", response)
        if conversation.title == "New Chat":
            conversation.title = request.message.strip().splitlines()[0][:60]
            db.commit()

        return {
            "response": response,
            "conversation_id": conversation.id,
        }

    finally:

        db.close()


@router.get("/conversations")
def list_conversations():
    db = next(get_db())
    try:
        result = []
        for item in crud.get_conversations(db, USER_ID):
            messages = crud.get_messages(db, item.id)
            result.append({"id": item.id, "title": item.title, "created_at": item.created_at, "updated_at": item.updated_at, "preview": messages[-1].content[:100] if messages else "Start a new study session"})
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
        return {"id": item.id, "title": item.title, "messages": [{"id": message.id, "role": message.role, "content": message.content, "created_at": message.created_at} for message in crud.get_messages(db, conversation_id)]}
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