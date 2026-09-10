from pydantic import BaseModel, Field


class ChatRequest(BaseModel):

    message: str = Field(
        min_length=1,
        max_length=20_000,
    )
    conversation_id: int | None = None


class ChatResponse(BaseModel):

    response: str
    conversation_id: int | None = None


class ConversationCreate(BaseModel):
    title: str = Field(default="New Chat", max_length=255)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class HealthResponse(BaseModel):

    status: str
    application: str