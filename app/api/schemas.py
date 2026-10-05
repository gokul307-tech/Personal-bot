from pydantic import BaseModel, Field
from typing import Literal


class ChatRequest(BaseModel):

    message: str = Field(
        min_length=1,
        max_length=20_000,
    )
    conversation_id: int | None = None
    source_filename: str | None = Field(default=None, max_length=255)
    preferences: "ChatPreferences" = Field(default_factory=lambda: ChatPreferences())
    auto_title: bool = True
    keep_attachment_context: bool = True


class ChatPreferences(BaseModel):
    response_style: Literal["simple", "balanced", "detailed"] = "balanced"
    answer_length: Literal["short", "medium", "detailed"] = "medium"
    default_exam_mode: Literal["2", "5", "10", "16"] = "5"
    beginner_friendly: bool = True
    prefer_uploaded_materials: bool = True
    show_sources: bool = True


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
    priority: Literal["low", "medium", "high"] = "medium"


class StudyPlanUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    subject: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=50_000)
    scheduled_at: str | None = None
    completed: bool | None = None
    priority: Literal["low", "medium", "high"] | None = None


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
    memory_type: str = Field(default="general", max_length=50)
    importance: float = Field(default=1.0, ge=0, le=10)


class HealthResponse(BaseModel):

    status: str
    application: str