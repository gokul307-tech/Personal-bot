from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.models import (
    CalendarEvent,
    Mark,
    Memory,
    Note,
    Reminder,
    StudyPlan,
    Conversation,
    Message,
)


def create_conversation(db: Session, user_id: int = 1, title: str = "New Chat"):
    conversation = Conversation(user_id=user_id, title=title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversations(db: Session, user_id: int = 1):
    query = select(Conversation).where(Conversation.user_id == user_id)
    return db.execute(query.order_by(Conversation.updated_at.desc())).scalars().all()


def get_conversation(db: Session, conversation_id: int, user_id: int = 1):
    return db.execute(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)).scalar_one_or_none()


def get_messages(db: Session, conversation_id: int):
    query = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc(), Message.id.asc())
    return db.execute(query).scalars().all()


def add_message(db: Session, conversation_id: int, role: str, content: str):
    message = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(message)
    conversation = db.get(Conversation, conversation_id)
    if conversation:
        conversation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    return message


def delete_conversation(db: Session, conversation_id: int, user_id: int = 1):
    conversation = get_conversation(db, conversation_id, user_id)
    if conversation is None:
        return False
    db.execute(delete(Message).where(Message.conversation_id == conversation_id))
    db.delete(conversation)
    db.commit()
    return True


def delete_all_conversations(db: Session, user_id: int = 1):
    conversations = get_conversations(db, user_id)
    ids = [conversation.id for conversation in conversations]
    if ids:
        db.execute(delete(Message).where(Message.conversation_id.in_(ids)))
        db.execute(delete(Conversation).where(Conversation.id.in_(ids)))
        db.commit()
    return len(ids)


def get_note(db: Session, note_id: int, user_id: int = 1):
    query = select(Note).where(Note.id == note_id)
    if user_id is not None:
        query = query.where(Note.user_id == user_id)
    return db.execute(query).scalar_one_or_none()


def delete_note(db: Session, note_id: int, user_id: int = 1) -> bool:
    note = get_note(db, note_id, user_id)
    if note is None:
        return False
    db.delete(note)
    db.commit()
    return True


def get_memory(db: Session, memory_id: int, user_id: int = 1):
    query = select(Memory).where(Memory.id == memory_id)
    if user_id is not None:
        query = query.where(Memory.user_id == user_id)
    return db.execute(query).scalar_one_or_none()


def delete_memory(db: Session, memory_id: int, user_id: int = 1) -> bool:
    memory = get_memory(db, memory_id, user_id)
    if memory is None:
        return False
    db.delete(memory)
    db.commit()
    return True


# =========================================================
# NOTES
# =========================================================

def create_note(
    db: Session,
    title: str,
    content: str,
    subject: str | None = None,
    user_id: int | None = None,
):

    note = Note(
        title=title,
        content=content,
        subject=subject,
        user_id=user_id,
    )

    db.add(note)
    db.commit()
    db.refresh(note)

    return note


def get_notes(
    db: Session,
    subject: str | None = None,
    user_id: int | None = None,
):

    query = select(Note)

    if user_id is not None:
        query = query.where(Note.user_id == user_id)

    if subject:
        query = query.where(Note.subject == subject)

    query = query.order_by(Note.created_at.desc())

    return db.execute(query).scalars().all()


# =========================================================
# MARKS
# =========================================================

def create_mark(
    db: Session,
    subject: str,
    marks_obtained: float,
    maximum_marks: float,
    exam_name: str | None = None,
    user_id: int | None = None,
):

    mark = Mark(
        subject=subject,
        marks_obtained=marks_obtained,
        maximum_marks=maximum_marks,
        exam_name=exam_name,
        user_id=user_id,
    )

    db.add(mark)
    db.commit()
    db.refresh(mark)

    return mark


def get_marks(
    db: Session,
    subject: str | None = None,
    user_id: int | None = None,
):

    query = select(Mark)

    if user_id is not None:
        query = query.where(Mark.user_id == user_id)

    if subject:
        query = query.where(Mark.subject == subject)

    query = query.order_by(Mark.created_at.desc())

    return db.execute(query).scalars().all()


# =========================================================
# STUDY PLANS
# =========================================================

def create_study_plan(
    db: Session,
    title: str,
    subject: str | None = None,
    description: str | None = None,
    scheduled_at: datetime | None = None,
    user_id: int | None = None,
):

    plan = StudyPlan(
        title=title,
        subject=subject,
        description=description,
        scheduled_at=scheduled_at,
        user_id=user_id,
    )

    db.add(plan)
    db.commit()
    db.refresh(plan)

    return plan


def get_study_plans(
    db: Session,
    user_id: int | None = None,
):

    query = select(StudyPlan)

    if user_id is not None:
        query = query.where(
            StudyPlan.user_id == user_id
        )

    query = query.order_by(
        StudyPlan.scheduled_at.asc()
    )

    return db.execute(query).scalars().all()


# =========================================================
# MEMORY
# =========================================================

def create_memory(
    db: Session,
    content: str,
    memory_type: str = "general",
    importance: float = 1.0,
    user_id: int | None = None,
):

    memory = Memory(
        content=content,
        memory_type=memory_type,
        importance=importance,
        user_id=user_id,
    )

    db.add(memory)
    db.commit()
    db.refresh(memory)

    return memory


def get_memories(
    db: Session,
    memory_type: str | None = None,
    user_id: int | None = None,
):

    query = select(Memory)

    if user_id is not None:
        query = query.where(
            Memory.user_id == user_id
        )

    if memory_type:
        query = query.where(
            Memory.memory_type == memory_type
        )

    query = query.order_by(
        Memory.importance.desc(),
        Memory.created_at.desc(),
    )

    return db.execute(query).scalars().all()


# =========================================================
# REMINDERS
# =========================================================

def create_reminder(
    db: Session,
    title: str,
    remind_at: datetime,
    description: str | None = None,
    user_id: int | None = None,
):

    reminder = Reminder(
        title=title,
        description=description,
        remind_at=remind_at,
        user_id=user_id,
    )

    db.add(reminder)
    db.commit()
    db.refresh(reminder)

    return reminder


def get_reminders(
    db: Session,
    user_id: int | None = None,
):

    query = select(Reminder)

    if user_id is not None:
        query = query.where(
            Reminder.user_id == user_id
        )

    query = query.order_by(
        Reminder.remind_at.asc()
    )

    return db.execute(query).scalars().all()


# =========================================================
# CALENDAR
# =========================================================

def create_calendar_event(
    db: Session,
    title: str,
    start_time: datetime,
    end_time: datetime | None = None,
    description: str | None = None,
    user_id: int | None = None,
):

    event = CalendarEvent(
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        user_id=user_id,
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    return event


def get_calendar_events(
    db: Session,
    user_id: int | None = None,
):

    query = select(CalendarEvent)

    if user_id is not None:
        query = query.where(
            CalendarEvent.user_id == user_id
        )

    query = query.order_by(
        CalendarEvent.start_time.asc()
    )

    return db.execute(query).scalars().all()