from sqlalchemy.orm import Session

from app.memory.long_term import LongTermMemory
from app.memory.short_term import ShortTermMemory


class MemoryManager:

    def __init__(self):

        self.short_term = ShortTermMemory()

        self.long_term = LongTermMemory()

    def add_message(
        self,
        role: str,
        content: str,
    ):

        self.short_term.add(
            role=role,
            content=content,
        )

    def get_conversation(self):

        return self.short_term.get_messages()

    def remember(
        self,
        db: Session,
        content: str,
        memory_type: str = "general",
        importance: float = 1.0,
        user_id: int | None = None,
    ):

        return self.long_term.remember(
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

        return self.long_term.recall(
            db=db,
            memory_type=memory_type,
            user_id=user_id,
        )