from sqlalchemy.orm import Session

from app.database.crud import (
    create_memory,
    get_memories,
)


def remember_information(
    db: Session,
    content: str,
    memory_type: str = "general",
    importance: float = 1.0,
    user_id: int | None = None,
) -> dict:

    if not content.strip():

        return {
            "success": False,
            "error": "Memory content cannot be empty.",
        }

    memory = create_memory(
        db=db,
        content=content,
        memory_type=memory_type,
        importance=importance,
        user_id=user_id,
    )

    return {
        "success": True,
        "id": memory.id,
        "content": memory.content,
        "memory_type": memory.memory_type,
        "importance": memory.importance,
    }


def recall_information(
    db: Session,
    memory_type: str | None = None,
    query: str | None = None,
    user_id: int | None = None,
) -> list[dict]:

    memories = get_memories(
        db=db,
        memory_type=memory_type,
        user_id=user_id,
    )

    result = [
        {
            "id": memory.id,
            "content": memory.content,
            "memory_type": memory.memory_type,
            "importance": memory.importance,
            "created_at": memory.created_at.isoformat(),
        }
        for memory in memories
    ]
    if query:
        query_text = query.casefold()
        result = [item for item in result if query_text in item["content"].casefold()]
    return result