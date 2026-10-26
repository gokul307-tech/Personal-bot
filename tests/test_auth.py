from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from werkzeug.security import check_password_hash

from app.api import auth, routes
from app.database import database
from app.database.database import Base
from app.database.models import AuthSession, LoginAttempt, User
from app.main import app


def _client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
        db.add(User(id=1, name="Legacy Local Data", is_legacy=True))
        db.commit()

    def get_test_db():
        yield factory()

    app.dependency_overrides[database.get_db] = get_test_db
    monkeypatch.setattr(auth, "get_db", get_test_db)
    monkeypatch.setattr(routes, "get_db", get_test_db)
    monkeypatch.setattr(database, "engine", engine)
    import app.main as main_module
    monkeypatch.setattr(main_module, "create_tables", lambda: None)
    return TestClient(app), factory


def test_registration_hashes_password_and_persistent_cookie_survives_new_client(monkeypatch):
    client, factory = _client(monkeypatch)
    try:
        registered = client.post("/api/auth/register", json={
            "username": "SageStudent",
            "password": "a-strong-password-123",
        })
        assert registered.status_code == 201
        assert registered.json() == {"id": 2, "username": "sagestudent"}
        set_cookie = registered.headers["set-cookie"].casefold()
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
        assert "max-age=" in set_cookie

        with factory() as db:
            user = db.execute(select(User).where(User.id == registered.json()["id"])).scalar_one()
            assert user.password_hash != "a-strong-password-123"
            assert check_password_hash(user.password_hash, "a-strong-password-123")
            session = db.execute(select(AuthSession).where(AuthSession.user_id == user.id)).scalar_one()
            assert session.token_hash not in client.cookies.get(auth.SESSION_COOKIE_NAME)

        duplicate = client.post("/api/auth/register", json={
            "username": "sagestudent",
            "password": "another-strong-password",
        })
        assert duplicate.status_code == 409

        restarted_client = TestClient(app)
        try:
            restarted_client.cookies.set(auth.SESSION_COOKIE_NAME, client.cookies.get(auth.SESSION_COOKIE_NAME))
            restored = restarted_client.get("/api/auth/session")
            assert restored.status_code == 200
            assert restored.json()["username"] == "sagestudent"
        finally:
            restarted_client.close()
    finally:
        client.close()


def test_failed_login_rate_limit_logout_and_session_expiry(monkeypatch):
    client, factory = _client(monkeypatch)
    try:
        client.post("/api/auth/register", json={
            "username": "study_user",
            "password": "another-strong-password",
        })
        client.post("/api/auth/logout")

        failed = client.post("/api/auth/login", json={
            "username": "study_user",
            "password": "incorrect-password-123",
        })
        assert failed.status_code == 401
        assert failed.json()["detail"] == "Invalid username or password."
        for _ in range(4):
            client.post("/api/auth/login", json={
                "username": "study_user",
                "password": "incorrect-password-123",
            })
        limited = client.post("/api/auth/login", json={
            "username": "study_user",
            "password": "incorrect-password-123",
        })
        assert limited.status_code == 429
        with factory() as db:
            attempt = db.query(LoginAttempt).one()
            attempt.locked_until = datetime.utcnow() - timedelta(seconds=1)
            db.commit()

        login = client.post("/api/auth/login", json={
            "username": "study_user",
            "password": "another-strong-password",
        })
        assert login.status_code == 200
        assert client.get("/api/auth/session").status_code == 200
        with factory() as db:
            session = db.execute(
                select(AuthSession)
                .where(AuthSession.user_id == login.json()["id"])
                .order_by(AuthSession.id.desc())
            ).scalars().first()
            session.expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        expired = client.get("/api/auth/session")
        assert expired.status_code == 401

        new_login = client.post("/api/auth/login", json={
            "username": "study_user",
            "password": "another-strong-password",
        })
        assert new_login.status_code == 200
        logged_out = client.post("/api/auth/logout")
        assert logged_out.status_code == 204
        assert client.get("/api/auth/session").status_code == 401
    finally:
        client.close()


def test_unauthenticated_private_api_is_rejected(monkeypatch):
    client, _factory = _client(monkeypatch)
    try:
        assert client.get("/api/notes").status_code == 401
        assert client.get("/api/conversations").status_code == 401
        assert client.post("/api/chat", json={"message": "private"}).status_code == 401
    finally:
        client.close()


def test_private_application_shell_requires_a_valid_session(monkeypatch):
    client, _factory = _client(monkeypatch)
    try:
        login_screen = client.get("/")
        assert login_screen.status_code == 200
        assert "auth-form" in login_screen.text
        assert 'id="app-shell"' not in login_screen.text
        assert 'id="app-shell"' not in client.get("/index.html").text

        registered = client.post("/api/auth/register", json={
            "username": "shell_user",
            "password": "a-strong-password-456",
        })
        assert registered.status_code == 201
        application = client.get("/")
        assert application.status_code == 200
        assert 'id="app-shell"' in application.text
        assert "auth-form" not in application.text
    finally:
        client.close()


def test_user_data_and_guessed_ids_are_isolated(monkeypatch):
    owner, _factory = _client(monkeypatch)
    other = TestClient(app)
    try:
        owner_auth = owner.post("/api/auth/register", json={
            "username": "owner_user",
            "password": "owner-strong-password",
        })
        other_auth = other.post("/api/auth/register", json={
            "username": "other_user",
            "password": "other-strong-password",
        })
        assert owner_auth.status_code == other_auth.status_code == 201

        note = owner.post("/api/notes", json={"title": "Private", "content": "Owner text"}).json()
        conversation = owner.post("/api/conversations", json={"title": "Owner chat"}).json()

        assert [item["title"] for item in owner.get("/api/notes").json()] == ["Private"]
        assert other.get("/api/notes").json() == []
        assert other.patch(f"/api/notes/{note['id']}", json={"title": "Stolen"}).status_code == 404
        assert other.get(f"/api/conversations/{conversation['id']}").status_code == 404
        assert [item["title"] for item in other.get("/api/conversations").json()] == []
    finally:
        owner.close()
        other.close()