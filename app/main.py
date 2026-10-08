from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from app.config.settings import BASE_DIR, validate_settings

from app.api.routes import router
from app.config.settings import APP_NAME
from app.database.database import create_tables


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
    def root():
        return FileResponse(BASE_DIR / "frontend" / "index.html")

    application.include_router(
        router,
        prefix="/api",
    )

    application.mount(
        "/assets",
        StaticFiles(directory=BASE_DIR / "frontend" / "public" / "assets"),
        name="assets",
    )

    application.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")

    return application


app = create_app()