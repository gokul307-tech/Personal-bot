from datetime import datetime

from sqlalchemy.orm import Session

from app.database.crud import (
    create_reminder,
    get_reminders,
)


def create_reminder_tool(
    db: Session,
    title: str,
    remind_at: str,
    description: str | None = None,
    user_id: int | None = None,
) -> dict:

    try:

        parsed_time = datetime.fromisoformat(
            remind_at
        )

    except ValueError:

        return {
            "success": False,
            "error": (
                "Invalid datetime. "
                "Use ISO format such as "
                "2026-08-15T18:00:00."
            ),
        }

    reminder = create_reminder(
        db=db,
        title=title,
        remind_at=parsed_time,
        description=description,
        user_id=user_id,
    )

    return {
        "success": True,
        "id": reminder.id,
        "title": reminder.title,
        "remind_at": reminder.remind_at.isoformat(),
    }


def list_reminders(
    db: Session,
    user_id: int | None = None,
) -> list[dict]:

    reminders = get_reminders(
        db=db,
        user_id=user_id,
    )

    return [
        {
            "id": reminder.id,
            "title": reminder.title,
            "description": reminder.description,
            "remind_at": reminder.remind_at.isoformat(),
            "completed": reminder.completed,
        }
        for reminder in reminders
    ]