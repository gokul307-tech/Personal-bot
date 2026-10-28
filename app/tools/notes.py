from sqlalchemy.orm import Session

from app.api.auth_context import current_user_id
from app.database.crud import (
    create_note,
    get_notes,
)


def add_note(
    db: Session,
    title: str,
    content: str,
    subject: str | None = None,
) -> dict:

    note = create_note(
        db=db,
        title=title,
        content=content,
        subject=subject,
        user_id=current_user_id(),
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
) -> list[dict]:

    notes = get_notes(
        db=db,
        subject=subject,
        user_id=current_user_id(),
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