from pydantic import BaseModel, Field, field_validator
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

    @field_validator("message")
    @classmethod
    def require_nonblank_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank.")
        return value


class ChatPreferences(BaseModel):
    response_style: Literal["simple", "balanced", "detailed"] = "balanced"
    answer_length: Literal["short", "medium", "detailed"] = "medium"
    default_exam_mode: Literal["2", "5", "10", "16"] = "5"
    beginner_friendly: bool = True
    prefer_uploaded_materials: bool = True
    show_sources: bool = True
    study_style: Literal["focused blocks", "short sessions", "deep work"] = "focused blocks"
    quiz_difficulty: Literal["easy", "medium", "hard"] = "medium"


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

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Title cannot be blank.")
        return value

    @field_validator("content")
    @classmethod
    def require_nonblank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content cannot be blank.")
        return value


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    content: str | None = Field(default=None, max_length=50_000)
    subject: str | None = Field(default=None, max_length=100)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Title cannot be blank.")
        return value

    @field_validator("content")
    @classmethod
    def require_nonblank_content(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Content cannot be blank.")
        return value


class StudyPlanCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    subject: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=50_000)
    scheduled_at: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Title cannot be blank.")
        return value


class StudyPlanUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    subject: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=50_000)
    scheduled_at: str | None = None
    completed: bool | None = None
    priority: Literal["low", "medium", "high"] | None = None


class StudyPlanRequest(BaseModel):
    request: str = Field(min_length=1, max_length=2_000)
    priority: Literal["low", "medium", "high"] = "medium"

    @field_validator("request")
    @classmethod
    def require_nonblank_request(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Study request cannot be blank.")
        return value


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
    memory_type: str = Field(default="general", max_length=50)
    importance: float = Field(default=1.0, ge=0, le=10)

    @field_validator("content")
    @classmethod
    def require_nonblank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Memory content cannot be blank.")
        return value


class HealthResponse(BaseModel):

    status: str
    application: str