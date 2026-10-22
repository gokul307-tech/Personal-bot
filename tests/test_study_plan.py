from datetime import date, datetime

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes
from app.api.schemas import StudyPlanBulkCreate, StudyPlanCreate, StudyPlanRequest, StudyPlanUpdate
from app.database.database import Base
from app.database.models import StudyPlan
from app.services.study_plan_service import categorize_study_plans, generate_study_schedule


def _database(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def get_test_db():
        yield factory()

    monkeypatch.setattr(routes, "get_db", get_test_db)
    return engine, factory


def test_study_plan_crud_and_owner_checks(monkeypatch):
    _engine, factory = _database(monkeypatch)
    created = routes.create_study_plan(StudyPlanCreate(
        title="Read chapter",
        subject="OS",
        scheduled_at="2026-10-22T18:00:00",
        priority="high",
        estimated_minutes=45,
    ))
    assert created["estimated_minutes"] == 45
    assert created["completed"] is False

    edited = routes.update_study_plan(created["id"], StudyPlanUpdate(
        title="Review chapter",
        priority="low",
        estimated_minutes=75,
    ))
    assert edited["title"] == "Review chapter"
    assert edited["priority"] == "low"
    assert edited["estimated_minutes"] == 75

    completed = routes.update_study_plan(created["id"], completed=True)
    assert completed["completed"] is True
    reopened = routes.update_study_plan(created["id"], completed=False)
    assert reopened["completed"] is False

    with pytest.raises(HTTPException) as error:
        routes.update_study_plan(999999, StudyPlanUpdate(title="Not mine"))
    assert error.value.status_code == 404

    foreign_task = StudyPlan(user_id=2, title="Private task", completed=False)
    with factory() as db:
        db.add(foreign_task)
        db.commit()
        db.refresh(foreign_task)
        foreign_id = foreign_task.id
    with pytest.raises(HTTPException) as error:
        routes.update_study_plan(foreign_id, StudyPlanUpdate(title="Changed"))
    assert error.value.status_code == 404

    assert routes.delete_study_plan(created["id"]) == {"deleted": True}
    with pytest.raises(HTTPException) as error:
        routes.delete_study_plan(created["id"])
    assert error.value.status_code == 404


def test_statistics_api_reports_correct_task_counts(monkeypatch):
    _database(monkeypatch)
    today = date(2026, 10, 21)
    for title, scheduled_at, completed in (
        ("Late", "2026-10-20T18:00:00", False),
        ("Due", "2026-10-21T18:00:00", False),
        ("Later", "2026-10-22T18:00:00", False),
        ("Done", "2026-10-20T18:00:00", True),
    ):
        task = routes.create_study_plan(StudyPlanCreate(title=title, scheduled_at=scheduled_at))
        if completed:
            routes.update_study_plan(task["id"], completed=True)

    stats = routes.study_plan_statistics(today=today)

    assert (stats["total"], stats["active"], stats["completed"]) == (4, 3, 1)
    assert (stats["overdue"], stats["due_today"], stats["upcoming"]) == (1, 1, 1)
    assert stats["completion_percentage"] == 25


def test_study_plan_statistics_categorize_dates_and_completed_tasks():
    plans = [
        {"id": 1, "completed": False, "scheduled_at": "2026-10-20T18:00:00"},
        {"id": 2, "completed": False, "scheduled_at": datetime(2026, 10, 21, 23, 59)},
        {"id": 3, "completed": False, "scheduled_at": "2026-10-22T00:00:00"},
        {"id": 4, "completed": False, "scheduled_at": None},
        {"id": 5, "completed": True, "scheduled_at": "2026-10-19T18:00:00"},
    ]

    result = categorize_study_plans(plans, date(2026, 10, 21))

    assert [task["id"] for task in result["groups"]["overdue"]] == [1]
    assert [task["id"] for task in result["groups"]["today"]] == [2]
    assert [task["id"] for task in result["groups"]["upcoming"]] == [3, 4]
    assert [task["id"] for task in result["groups"]["completed"]] == [5]
    assert result["total"] == 5
    assert result["active"] == 4
    assert result["completion_percentage"] == 20
    assert result["overdue"] + result["due_today"] + result["upcoming"] == result["active"]


def test_study_plan_preview_and_bulk_save_prevent_duplicates(monkeypatch):
    _database(monkeypatch)
    request = StudyPlanRequest(request="I have 3 days to prepare for OS", priority="high")
    preview = routes.preview_study_plan(request)
    assert len(preview["tasks"]) == 3
    assert {task["subject"] for task in preview["tasks"]} == {"OS"}
    assert {task["priority"] for task in preview["tasks"]} == {"high"}
    assert all(task["estimated_minutes"] > 0 for task in preview["tasks"])
    assert routes.list_study_plans() == []

    first_save = routes.create_study_plan_tasks(StudyPlanBulkCreate(tasks=preview["tasks"]))
    second_save = routes.create_study_plan_tasks(StudyPlanBulkCreate(tasks=preview["tasks"]))

    assert first_save["created"] == 3
    assert first_save["duplicates"] == 0
    assert second_save["created"] == 0
    assert second_save["duplicates"] == 3
    assert len(routes.list_study_plans()) == 3


def test_study_schedule_duration_and_subject_are_bounded():
    generated = generate_study_schedule(
        "I have 2 weeks to prepare for Operating Systems",
        "medium",
        start_date=date(2026, 10, 21),
    )

    assert len(generated) == 14
    assert generated[0]["subject"] == "Operating Systems"
    assert generated[0]["scheduled_at"] == "2026-10-21T18:00:00"
    assert generated[-1]["scheduled_at"] == "2026-11-03T18:00:00"


def test_study_schedule_parses_daily_duration_and_subject():
    hourly = generate_study_schedule(
        "I have 3 days to prepare for OS, 2 hours each day",
        "high",
        start_date=date(2026, 10, 21),
    )
    minute = generate_study_schedule(
        "Study biology for 90 minutes daily for 5 days",
        "medium",
        start_date=date(2026, 10, 21),
    )

    assert len(hourly) == 3
    assert all(task["subject"] == "OS" and task["estimated_minutes"] == 120 for task in hourly)
    assert len(minute) == 5
    assert all(task["subject"] == "biology" and task["estimated_minutes"] == 90 for task in minute)


def test_existing_study_plan_schema_is_migrated_without_losing_data(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE study_plans ("
            "id INTEGER PRIMARY KEY, user_id INTEGER, title VARCHAR(255) NOT NULL, "
            "subject VARCHAR(100), description TEXT, scheduled_at DATETIME, completed BOOLEAN)"
        ))
        connection.execute(text(
            "INSERT INTO study_plans (id, user_id, title, completed) VALUES (1, 1, 'Keep me', 0)"
        ))
    monkeypatch.setattr("app.database.database.engine", engine)

    from app.database.database import create_tables

    create_tables()

    columns = {column["name"] for column in inspect(engine).get_columns("study_plans")}
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT title, priority, estimated_minutes FROM study_plans WHERE id = 1"
        )).one()
    assert {"priority", "estimated_minutes"} <= columns
    assert row == ("Keep me", "medium", 60)
