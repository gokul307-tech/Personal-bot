from fastapi import FastAPI

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

        return {
            "application": APP_NAME,
            "status": "running",
            "message": "VDSS AI Agent is running.",
            "docs": "/docs",
        }

    application.include_router(
        router,
        prefix="/api",
    )

    return application


app = create_app()