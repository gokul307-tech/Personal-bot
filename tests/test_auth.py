from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from werkzeug.security import check_password_hash

from app.api import auth, routes
from app.database import database
from app.database.database import Base
from app.database.models import AuthSession, LoginAttempt, User
from app.main import app
from app.rag import vector_store


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
        assert client.get("/api/notes").status_code == 401
        with factory() as db:
            latest_session = db.execute(
                select(AuthSession)
                .where(AuthSession.user_id == new_login.json()["id"])
                .order_by(AuthSession.id.desc())
            ).scalars().first()
            assert latest_session.revoked_at is not None
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


def test_cross_origin_mutations_are_rejected(monkeypatch):
    client, _factory = _client(monkeypatch)
    try:
        rejected_registration = client.post(
            "/api/auth/register",
            headers={"Origin": "https://attacker.example"},
            json={"username": "csrf_user", "password": "csrf-password-123"},
        )
        assert rejected_registration.status_code == 403

        registered = client.post("/api/auth/register", json={
            "username": "csrf_user",
            "password": "csrf-password-123",
        })
        assert registered.status_code == 201
        rejected_write = client.post(
            "/api/notes",
            headers={"Origin": "https://attacker.example"},
            json={"title": "Cross-site", "content": "must not be saved"},
        )
        assert rejected_write.status_code == 403
        assert client.get("/api/notes").json() == []
    finally:
        client.close()


def test_session_cookie_is_secure_in_production(monkeypatch):
    client, _factory = _client(monkeypatch)
    monkeypatch.setattr(auth, "APP_ENV", "production")
    try:
        response = client.post("/api/auth/register", json={
            "username": "secure_cookie",
            "password": "secure-cookie-password",
        })
        assert response.status_code == 201
        assert "; secure" in response.headers["set-cookie"].casefold()
        assert "httponly" in response.headers["set-cookie"].casefold()
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
        assert 'id="app-shell"' in client.get("/login.html").text
        assert application.headers["cache-control"] == "no-store"
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
        assert other.delete(f"/api/conversations/{conversation['id']}").status_code == 404
        assert owner.get(f"/api/conversations/{conversation['id']}").status_code == 200
        assert [item["title"] for item in other.get("/api/conversations").json()] == []

        plan = owner.post("/api/study-plans", json={"title": "Owner plan"}).json()
        memory = owner.post("/api/memories", json={"content": "Owner memory"}).json()
        assert other.get("/api/study-plans").json() == []
        assert other.get("/api/memories").json() == []
        assert other.patch(f"/api/study-plans/{plan['id']}", json={"title": "Stolen"}).status_code == 404
        assert other.delete(f"/api/memories/{memory['id']}").status_code == 404
    finally:
        owner.close()
        other.close()


def test_uploaded_documents_and_note_pdfs_are_owned_by_their_creator(monkeypatch, tmp_path):
    owner, _factory = _client(monkeypatch)
    other = TestClient(app)
    try:
        owner_auth = owner.post("/api/auth/register", json={
            "username": "file_owner",
            "password": "file-owner-password",
        })
        other_auth = other.post("/api/auth/register", json={
            "username": "file_other",
            "password": "file-other-password",
        })
        assert owner_auth.status_code == other_auth.status_code == 201

        monkeypatch.setattr(routes, "DOCUMENTS_DIR", tmp_path / "documents")
        monkeypatch.setattr(routes, "NOTE_ATTACHMENTS_DIR", tmp_path / "note-attachments")
        monkeypatch.setattr(routes, "get_all_documents", lambda _owner_id=None: [])
        monkeypatch.setattr(routes, "delete_documents_by_filename", lambda *_args: 0)
        monkeypatch.setattr(routes, "ingest_document", lambda *_args, **_kwargs: {"success": True})
        monkeypatch.setattr(routes, "read_pdf_pages", lambda _path: [])

        uploaded = owner.post(
            "/api/documents",
            files={"file": ("private.txt", b"owner document", "text/plain")},
        )
        assert uploaded.status_code == 200
        assert owner.get("/api/documents/private.txt/open").content == b"owner document"
        assert other.get("/api/documents").json() == []
        assert other.get("/api/documents/private.txt/open").status_code == 404
        other.delete("/api/documents/private.txt")
        assert owner.get("/api/documents/private.txt/open").status_code == 200

        note_response = owner.post(
            "/api/notes/with-pdf",
            data={"title": "Private PDF note", "content": "owner-only"},
            files={"file": ("private.pdf", b"test pdf bytes", "application/pdf")},
        )
        assert note_response.status_code == 200
        note_id = note_response.json()["id"]
        pdf_path = next((tmp_path / "note-attachments").glob("*.pdf"))
        assert owner.get(f"/api/notes/{note_id}/pdf").content == b"test pdf bytes"
        assert other.get(f"/api/notes/{note_id}/pdf").status_code == 404
        assert other.delete(f"/api/notes/{note_id}").status_code == 404
        assert pdf_path.is_file()
    finally:
        owner.close()
        other.close()


def test_legacy_rows_migrate_to_unavailable_legacy_owner(monkeypatch, tmp_path):
    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    legacy_tables = (
        "notes",
        "marks",
        "study_plans",
        "memories",
        "reminders",
        "calendar_events",
        "conversations",
    )
    with legacy_engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "email TEXT, created_at DATETIME)"
        ))
        connection.execute(text(
            "INSERT INTO users (id, name, created_at) VALUES (7, 'Old user', CURRENT_TIMESTAMP)"
        ))
        for table in legacy_tables:
            connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)"))
            connection.execute(text(f"INSERT INTO {table} (id) VALUES (1)"))

    monkeypatch.setattr(database, "engine", legacy_engine)
    monkeypatch.setattr("app.rag.vector_store.assign_legacy_owner", lambda _owner_id: 0)
    try:
        database.create_tables()
        inspector = inspect(legacy_engine)
        for table in legacy_tables:
            assert "user_id" in {column["name"] for column in inspector.get_columns(table)}
        with legacy_engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == 2
            assert connection.execute(text(
                "SELECT is_legacy FROM users WHERE id = 1"
            )).scalar_one() == 1
            for table in legacy_tables:
                assert connection.execute(
                    text(f"SELECT user_id FROM {table} WHERE id = 1")
                ).scalar_one() == 1
    finally:
        legacy_engine.dispose()


def test_legacy_vector_documents_are_not_visible_to_new_users(monkeypatch, tmp_path):
    monkeypatch.setattr(vector_store, "STORE_FILE", tmp_path / "vectors.json")
    vector_store.add_documents([
        {"filename": "legacy.txt", "text": "legacy_only_material"},
        {"filename": "owned.txt", "owner_id": 2, "text": "new private content"},
    ])

    assert vector_store.assign_legacy_owner(1) == 1
    assert [item["filename"] for item in vector_store.get_all_documents(1)] == ["legacy.txt"]
    assert [item["filename"] for item in vector_store.get_all_documents(2)] == ["owned.txt"]
    assert vector_store.search([], query_text="legacy_only_material", owner_id=2) == []