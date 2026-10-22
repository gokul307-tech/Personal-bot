from datetime import date, datetime, time, timedelta
import re
from typing import Any, Sequence


def _scheduled_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def categorize_study_plans(
    plans: Sequence[dict[str, Any]],
    today: date,
) -> dict[str, Any]:
    completed = [plan for plan in plans if plan.get("completed")]
    active = [plan for plan in plans if not plan.get("completed")]
    overdue = []
    due_today = []
    upcoming = []

    for plan in active:
        scheduled_date = _scheduled_date(plan.get("scheduled_at"))
        if scheduled_date is not None and scheduled_date < today:
            overdue.append(plan)
        elif scheduled_date == today:
            due_today.append(plan)
        else:
            upcoming.append(plan)

    total = len(plans)
    completed_count = len(completed)
    return {
        "total": total,
        "completed": completed_count,
        "active": len(active),
        "overdue": len(overdue),
        "due_today": len(due_today),
        "upcoming": len(upcoming),
        "completion_percentage": round(completed_count / total * 100) if total else 0,
        "groups": {
            "overdue": overdue,
            "today": due_today,
            "upcoming": upcoming,
            "completed": completed,
        },
    }


def generate_study_schedule(
    request: str,
    priority: str,
    start_date: date | None = None,
) -> list[dict[str, Any]]:
    duration_match = re.search(r"\b(\d{1,2})\s*(days?|weeks?)\b", request, re.IGNORECASE)
    daily_duration_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\s*(?:(?:each|per)\s+day|daily|a\s+day|/day)\b",
        request,
        re.IGNORECASE,
    )
    estimated_minutes = 60
    if daily_duration_match:
        amount = float(daily_duration_match.group(1))
        unit = daily_duration_match.group(2).casefold()
        estimated_minutes = round(amount * 60) if unit.startswith(("hour", "hr")) else round(amount)
        estimated_minutes = min(max(estimated_minutes, 5), 1440)

    days = 1
    if duration_match:
        days = int(duration_match.group(1))
        if duration_match.group(2).lower().startswith("week"):
            days *= 7
    days = min(max(days, 1), 30)

    topic_patterns = (
        r"\bprepare(?:\s+for)?\s+(.+?)(?=[.!?,;:]|$)",
        r"\bstudy\s+(?:for\s+)?(.+?)(?=[.!?,;:]|$)",
        r"\brevise\s+(.+?)(?=[.!?,;:]|$)",
    )
    subject_request = re.sub(
        r"\s+(?:for\s+)?\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?)\s*(?:(?:each|per)\s+day|daily|a\s+day|/day)\b",
        "",
        request,
        flags=re.IGNORECASE,
    )
    subject = None
    for pattern in topic_patterns:
        match = re.search(pattern, subject_request, re.IGNORECASE)
        if match:
            subject = match.group(1).strip()
            subject = re.sub(r"^(?:in|over|within)\s+\d+\s+\w+\s+(?:to\s+)?", "", subject, flags=re.IGNORECASE)
            subject = re.sub(r"^(?:for\s+)", "", subject, flags=re.IGNORECASE).strip()
            if subject:
                break
    subject = subject or "General"
    subject = re.sub(r"\s+(?:in|over|within|for)\s+\d+\s+(?:days?|weeks?).*$", "", subject, flags=re.IGNORECASE).strip()
    if start_date is None:
        now = datetime.now()
        start = now.date() + timedelta(days=1 if now.hour >= 18 else 0)
    else:
        start = start_date
    activities = (
        ("Review core concepts", "Review the core concepts and identify topics to revisit."),
        ("Practice key questions", "Practice representative questions and review mistakes."),
        ("Recap and self-test", "Revisit weak areas and complete a timed self-test."),
    )

    tasks = []
    for index in range(days):
        activity, description = activities[index % len(activities)]
        due = datetime.combine(start + timedelta(days=index), time(hour=18))
        tasks.append({
            "title": f"{subject} - Day {index + 1}: {activity}" if days > 1 else f"Study {subject}: {activity}",
            "subject": subject,
            "description": description,
            "scheduled_at": due.isoformat(),
            "priority": priority,
            "estimated_minutes": estimated_minutes,
        })
    return tasks
