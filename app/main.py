from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.config.settings import BASE_DIR

from app.api.routes import router
from app.config.settings import APP_NAME
from app.database.database import create_tables


def create_app() -> FastAPI:

    create_tables()

    application = FastAPI(
        title=APP_NAME,
        description=(
            "VDSS - Virtual Digital Study System "
            "AI Agent"
        ),
        version="1.0.0",
    )

    @application.get("/")
    def root():
        return FileResponse(BASE_DIR / "frontend" / "index.html")

    application.include_router(
        router,
        prefix="/api",
    )

    application.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")

    return application


app = create_app()