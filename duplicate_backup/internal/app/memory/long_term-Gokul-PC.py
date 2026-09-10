from sqlalchemy.orm import Session

from app.database.crud import (
    create_memory,
    get_memories,
)


class LongTermMemory:

    def remember(
        self,
        db: Session,
        content: str,
        memory_type: str = "general",
        importance: float = 1.0,
        user_id: int | None = None,
    ):

        return create_memory(
            db=db,
            content=content,
            memory_type=memory_type,
            importance=importance,
            user_id=user_id,
        )

    def recall(
        self,
        db: Session,
        memory_type: str | None = None,
        user_id: int | None = None,
    ):

        return get_memories(
            db=db,
            memory_type=memory_type,
            user_id=user_id,
        )