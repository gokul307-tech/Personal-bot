from datetime import datetime

from sqlalchemy.orm import Session

from app.database.crud import (
    create_study_plan,
    get_study_plans,
)


def create_plan(
    db: Session,
    title: str,
    subject: str | None = None,
    description: str | None = None,
    scheduled_at: str | None = None,
    user_id: int | None = None,
) -> dict:

    parsed_datetime = None

    if scheduled_at:

        try:
            parsed_datetime = datetime.fromisoformat(
                scheduled_at
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

    plan = create_study_plan(
        db=db,
        title=title,
        subject=subject,
        description=description,
        scheduled_at=parsed_datetime,
        user_id=user_id,
    )

    return {
        "success": True,
        "id": plan.id,
        "title": plan.title,
        "subject": plan.subject,
        "description": plan.description,
        "scheduled_at": (
            plan.scheduled_at.isoformat()
            if plan.scheduled_at
            else None
        ),
    }


def list_plans(
    db: Session,
    user_id: int | None = None,
) -> list[dict]:

    plans = get_study_plans(
        db=db,
        user_id=user_id,
    )

    return [
        {
            "id": plan.id,
            "title": plan.title,
            "subject": plan.subject,
            "description": plan.description,
            "scheduled_at": (
                plan.scheduled_at.isoformat()
                if plan.scheduled_at
                else None
            ),
            "completed": plan.completed,
        }
        for plan in plans
    ]