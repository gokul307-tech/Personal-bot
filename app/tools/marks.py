from sqlalchemy.orm import Session

from app.database.crud import (
    create_mark,
    get_marks,
)


def add_mark(
    db: Session,
    subject: str,
    marks_obtained: float,
    maximum_marks: float,
    exam_name: str | None = None,
    user_id: int | None = None,
) -> dict:

    if maximum_marks <= 0:
        return {
            "success": False,
            "error": "Maximum marks must be greater than zero.",
        }

    if marks_obtained < 0:
        return {
            "success": False,
            "error": "Marks obtained cannot be negative.",
        }

    if marks_obtained > maximum_marks:
        return {
            "success": False,
            "error": "Marks obtained cannot exceed maximum marks.",
        }

    mark = create_mark(
        db=db,
        subject=subject,
        marks_obtained=marks_obtained,
        maximum_marks=maximum_marks,
        exam_name=exam_name,
        user_id=user_id,
    )

    percentage = (
        marks_obtained / maximum_marks
    ) * 100

    return {
        "success": True,
        "id": mark.id,
        "subject": mark.subject,
        "exam_name": mark.exam_name,
        "marks_obtained": mark.marks_obtained,
        "maximum_marks": mark.maximum_marks,
        "percentage": round(percentage, 2),
    }


def list_marks(
    db: Session,
    subject: str | None = None,
    user_id: int | None = None,
) -> list[dict]:

    marks = get_marks(
        db=db,
        subject=subject,
        user_id=user_id,
    )

    return [
        {
            "id": mark.id,
            "subject": mark.subject,
            "exam_name": mark.exam_name,
            "marks_obtained": mark.marks_obtained,
            "maximum_marks": mark.maximum_marks,
            "percentage": round(
                (
                    mark.marks_obtained
                    / mark.maximum_marks
                )
                * 100,
                2,
            ),
            "created_at": mark.created_at.isoformat(),
        }
        for mark in marks
    ]