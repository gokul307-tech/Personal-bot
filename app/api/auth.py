from datetime import datetime, timedelta
import hashlib
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from app.api.auth_context import reset_current_user_id, set_current_user_id
from app.config.settings import APP_ENV, AUTH_SESSION_DAYS, PUBLIC_ORIGIN
from app.database.database import get_db
from app.database.models import AuthSession, LoginAttempt, User


router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_COOKIE_NAME = "sage_session"
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_LOCKOUT = timedelta(minutes=15)
MAX_LOGIN_FAILURES = 5
_DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-user-password", method="scrypt")


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[a-z0-9_.-]{3,32}", normalized):
            raise ValueError("Username must be 3-32 letters, numbers, dots, dashes, or underscores.")
        return normalized


def _user_response(user: User) -> dict[str, int | str]:
    return {"id": user.id, "username": user.username or user.name}


def _check_origin(request: Request) -> None:
    if request.headers.get("sec-fetch-site", "").casefold() == "cross-site":
        raise HTTPException(status_code=403, detail="Cross-site request rejected.")
    origin = request.headers.get("origin")
    if not origin:
        return
    expected = (PUBLIC_ORIGIN or str(request.base_url)).rstrip("/")
    if origin.rstrip("/") != expected:
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")


def _session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def resolve_session_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    session = db.execute(
        select(AuthSession).where(
            AuthSession.token_hash == _session_hash(token),
            AuthSession.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    now = datetime.utcnow()
    user = db.get(User, session.user_id) if session else None
    if session is None:
        return None
    if session.expires_at <= now or user is None or user.is_legacy:
        if session.revoked_at is None:
            session.revoked_at = now
            db.commit()
        return None
    return user


def _attempt_key(username: str, remote_host: str) -> str:
    return hashlib.sha256(f"{username}\0{remote_host}".encode("utf-8")).hexdigest()


def _set_session(response: Response, db: Session, user: User) -> None:
    token = secrets.token_urlsafe(48)
    expires_at = datetime.utcnow() + timedelta(days=AUTH_SESSION_DAYS)
    db.add(AuthSession(user_id=user.id, token_hash=_session_hash(token), expires_at=expires_at))
    db.commit()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=AUTH_SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=APP_ENV in {"production", "prod"},
        samesite="lax",
        path="/",
    )


def _check_login_limit(db: Session, key: str, now: datetime) -> LoginAttempt:
    attempt = db.get(LoginAttempt, key)
    if attempt is None:
        attempt = LoginAttempt(key_hash=key, failures=0, window_started_at=now)
        db.add(attempt)
        db.flush()
    if attempt.locked_until and attempt.locked_until > now:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    if now - attempt.window_started_at > LOGIN_WINDOW or (attempt.locked_until and attempt.locked_until <= now):
        attempt.failures = 0
        attempt.window_started_at = now
        attempt.locked_until = None
    return attempt


def _record_login_failure(db: Session, attempt: LoginAttempt, now: datetime) -> None:
    attempt.failures += 1
    if attempt.failures >= MAX_LOGIN_FAILURES:
        attempt.locked_until = now + LOGIN_LOCKOUT
    db.commit()


@router.post("/register", status_code=201)
def register(credentials: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    _check_origin(request)
    username = credentials.username
    user = User(
        name=username,
        username=username,
        password_hash=generate_password_hash(credentials.password, method="scrypt"),
        is_legacy=False,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That username is already registered.") from exc
    _set_session(response, db, user)
    return _user_response(user)


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    _check_origin(request)
    username = credentials.username
    now = datetime.utcnow()
    host = request.client.host if request.client else "unknown"
    attempt = _check_login_limit(db, _attempt_key(username, host), now)
    user = db.execute(select(User).where(User.username == username, User.is_legacy.is_(False))).scalar_one_or_none()
    password_hash = user.password_hash if user and user.password_hash else _DUMMY_PASSWORD_HASH
    valid_password = check_password_hash(password_hash, credentials.password)
    if user is None or not user.password_hash or not valid_password:
        _record_login_failure(db, attempt, now)
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    db.delete(attempt)
    _set_session(response, db, user)
    return _user_response(user)


@router.get("/session")
def session_status(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = resolve_session_user(db, token)
    if user is None:
        if token:
            response.delete_cookie(SESSION_COOKIE_NAME, path="/", httponly=True, secure=APP_ENV in {"production", "prod"}, samesite="lax")
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    return _user_response(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    _check_origin(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        session = db.execute(select(AuthSession).where(AuthSession.token_hash == _session_hash(token))).scalar_one_or_none()
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.utcnow()
            db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", httponly=True, secure=APP_ENV in {"production", "prod"}, samesite="lax")
    response.status_code = 204
    return response


async def require_authenticated(request: Request, response: Response, db: Session = Depends(get_db)):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        _check_origin(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = resolve_session_user(db, token)
    if user is None:
        if token:
            response.delete_cookie(SESSION_COOKIE_NAME, path="/", httponly=True, secure=APP_ENV in {"production", "prod"}, samesite="lax")
        raise HTTPException(status_code=401, detail="Authentication required.")

    context_token = set_current_user_id(user.id)
    try:
        yield user
    finally:
        reset_current_user_id(context_token)