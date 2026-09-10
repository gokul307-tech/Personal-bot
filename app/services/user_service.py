from sqlalchemy.orm import Session

from app.database.models import User


def create_user(
    db: Session,
    name: str,
    email: str | None = None,
) -> User:

    user = User(
        name=name,
        email=email,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user