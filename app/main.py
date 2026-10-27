from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from app.config.settings import BASE_DIR, validate_settings

from app.api.routes import router
from app.api.auth import SESSION_COOKIE_NAME, require_authenticated, resolve_session_user, router as auth_router
from app.config.settings import APP_NAME
from app.database.database import create_tables, get_db
from app.config.settings import APP_ENV


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        try:
            validate_settings()
            create_tables()
        except Exception as exc:
            logger.exception("SAGE startup initialization failed")
            raise RuntimeError(
                "SAGE could not start. Check application settings and database access."
            ) from exc
        yield

    application = FastAPI(
        title=APP_NAME,
        description=(
            "VDSS - Virtual Digital Study System "
            "AI Agent"
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def disable_private_response_caching(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/") or request.url.path in {
            "/",
            "/index.html",
            "/login.html",
        }:
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception):
        logger.error(
            "Unhandled application error",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "SAGE encountered an unexpected error. Please try again."},
        )

    @application.get("/")
    @application.get("/index.html")
    @application.get("/login.html")
    def frontend_shell(request: Request, response: Response, db=Depends(get_db)):
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if resolve_session_user(db, token) is not None:
            return FileResponse(BASE_DIR / "frontend" / "index.html")
        login_page = FileResponse(BASE_DIR / "frontend" / "login.html")
        if token:
            login_page.delete_cookie(
                SESSION_COOKIE_NAME,
                path="/",
                httponly=True,
                secure=APP_ENV in {"production", "prod"},
                samesite="lax",
            )
        return login_page

    application.include_router(auth_router, prefix="/api")
    application.include_router(
        router,
        prefix="/api",
        dependencies=[Depends(require_authenticated)],
    )

    application.mount(
        "/assets",
        StaticFiles(directory=BASE_DIR / "frontend" / "public" / "assets"),
        name="assets",
    )

    application.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")

    return application


app = create_app()