import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.question_types import QuestionType


class CultureFitTemplateCreate(BaseModel):
    title: str
    description: str | None = None
    instructions: str | None = None
    time_limit_minutes: int | None = Field(default=None, ge=1, le=480)


class CultureFitTemplateUpdate(BaseModel):
    title: str
    description: str | None = None
    instructions: str | None = None
    time_limit_minutes: int | None = Field(default=None, ge=1, le=480)


class CultureFitQuestionCreate(BaseModel):
    order_index: int = Field(ge=0)
    prompt: str = Field(min_length=1, max_length=4000)
    question_type: QuestionType
    config: dict | None = None
    time_limit_seconds: int | None = Field(default=None, ge=5, le=3600)


class CultureFitQuestionUpdate(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    question_type: QuestionType
    config: dict | None = None
    time_limit_seconds: int | None = Field(default=None, ge=5, le=3600)


class CultureFitQuestionsReorder(BaseModel):
    """The template's full question-id list in the desired order."""

    question_ids: list[uuid.UUID]


class CultureFitQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_index: int
    prompt: str = Field(min_length=1, max_length=4000)
    question_type: str
    config: dict | None
    time_limit_seconds: int | None


class CultureFitTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    instructions: str | None
    time_limit_minutes: int | None
    questions: list[CultureFitQuestionOut]
    created_at: datetime
    updated_at: datetime
