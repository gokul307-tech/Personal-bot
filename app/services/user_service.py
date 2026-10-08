from sqlalchemy.orm import Session

from app.database.models import User


def create_user(
    db: Session,
    name: str,
    email: str | None = None,
) -> User:

    name = name.strip() if isinstance(name, str) else ""
    if not name:
        raise ValueError("User name must not be blank.")
    if len(name) > 100:
        raise ValueError("User name must be 100 characters or fewer.")
    email = email.strip().lower() if email else None
    if email and len(email) > 255:
        raise ValueError("Email must be 255 characters or fewer.")

    user = User(
        name=name,
        email=email,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user