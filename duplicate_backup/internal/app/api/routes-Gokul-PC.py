from fastapi import APIRouter, Depends

from app.api.dependencies import get_agent
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
)
from app.config.settings import APP_NAME
from app.database.database import get_db
from app.agent.agent import VDSSAgent


router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
)
def health():

    return {
        "status": "ok",
        "application": APP_NAME,
    }


@router.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
    agent: VDSSAgent = Depends(get_agent),
):

    db_generator = get_db()

    db = next(db_generator)

    try:

        response = agent.run(
            user_message=request.message,
            db=db,
        )

        return {
            "response": response
        }

    finally:

        db.close()