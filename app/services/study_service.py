from sqlalchemy.orm import Session

from app.database.crud import (
    get_marks,
    get_notes,
    get_study_plans,
)


def get_study_summary(
    db: Session,
    user_id: int | None = None,
) -> dict:

    notes = get_notes(
        db=db,
        user_id=user_id,
    )

    marks = get_marks(
        db=db,
        user_id=user_id,
    )

    plans = get_study_plans(
        db=db,
        user_id=user_id,
    )

    total_obtained = sum(
        mark.marks_obtained
        for mark in marks
    )

    total_maximum = sum(
        mark.maximum_marks
        for mark in marks
    )

    percentage = (
        (
            total_obtained
            / total_maximum
        )
        * 100
        if total_maximum
        else 0
    )

    return {
        "notes_count": len(notes),
        "marks_count": len(marks),
        "study_plans_count": len(plans),
        "overall_percentage": round(
            percentage,
            2,
        ),
    }