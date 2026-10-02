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


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=50_000)
    subject: str | None = Field(default=None, max_length=100)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    content: str | None = Field(default=None, max_length=50_000)
    subject: str | None = Field(default=None, max_length=100)


class StudyPlanCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    subject: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=50_000)
    scheduled_at: str | None = None


class StudyPlanUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    subject: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=50_000)
    scheduled_at: str | None = None
    completed: bool | None = None


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
    memory_type: str = Field(default="general", max_length=50)
    importance: float = Field(default=1.0, ge=0, le=10)


class HealthResponse(BaseModel):

    status: str
    application: str