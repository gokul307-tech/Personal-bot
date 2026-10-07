from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.config.settings import BASE_DIR

from app.api.routes import router
from app.config.settings import APP_NAME
from app.database.database import create_tables


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        create_tables()
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