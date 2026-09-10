from datetime import datetime

from sqlalchemy.orm import Session

from app.database.crud import (
    create_calendar_event,
    get_calendar_events,
)


def create_event(
    db: Session,
    title: str,
    start_time: str,
    end_time: str | None = None,
    description: str | None = None,
    user_id: int | None = None,
) -> dict:

    try:

        parsed_start = datetime.fromisoformat(
            start_time
        )

        parsed_end = None

        if end_time:
            parsed_end = datetime.fromisoformat(
                end_time
            )

    except ValueError:

        return {
            "success": False,
            "error": "Invalid datetime format.",
        }

    event = create_calendar_event(
        db=db,
        title=title,
        start_time=parsed_start,
        end_time=parsed_end,
        description=description,
        user_id=user_id,
    )

    return {
        "success": True,
        "id": event.id,
        "title": event.title,
        "start_time": event.start_time.isoformat(),
        "end_time": (
            event.end_time.isoformat()
            if event.end_time
            else None
        ),
    }


def list_events(
    db: Session,
    user_id: int | None = None,
) -> list[dict]:

    events = get_calendar_events(
        db=db,
        user_id=user_id,
    )

    return [
        {
            "id": event.id,
            "title": event.title,
            "description": event.description,
            "start_time": event.start_time.isoformat(),
            "end_time": (
                event.end_time.isoformat()
                if event.end_time
                else None
            ),
        }
        for event in events
    ]