from sqlalchemy.orm import Session

from app.database.crud import (
    create_note,
    get_notes,
)


def add_note(
    db: Session,
    title: str,
    content: str,
    subject: str | None = None,
    user_id: int | None = None,
) -> dict:

    note = create_note(
        db=db,
        title=title,
        content=content,
        subject=subject,
        user_id=user_id,
    )

    return {
        "success": True,
        "id": note.id,
        "title": note.title,
        "subject": note.subject,
        "message": "Note created successfully.",
    }


def list_notes(
    db: Session,
    subject: str | None = None,
    user_id: int | None = None,
) -> list[dict]:

    notes = get_notes(
        db=db,
        subject=subject,
        user_id=user_id,
    )

    return [
        {
            "id": note.id,
            "title": note.title,
            "subject": note.subject,
            "content": note.content,
            "created_at": note.created_at.isoformat(),
        }
        for note in notes
    ]