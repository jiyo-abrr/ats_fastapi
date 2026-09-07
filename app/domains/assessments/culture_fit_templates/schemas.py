import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.question_types import QuestionType


class CultureFitTemplateCreate(BaseModel):
    title: str
    description: str | None = None
    instructions: str | None = None
    time_limit_minutes: int | None = None


class CultureFitTemplateUpdate(BaseModel):
    title: str
    description: str | None = None
    instructions: str | None = None
    time_limit_minutes: int | None = None


class CultureFitQuestionCreate(BaseModel):
    order_index: int
    prompt: str
    question_type: QuestionType
    config: dict | None = None
    time_limit_seconds: int | None = None


class CultureFitQuestionUpdate(BaseModel):
    prompt: str
    question_type: QuestionType
    config: dict | None = None
    time_limit_seconds: int | None = None


class CultureFitQuestionsReorder(BaseModel):
    """The template's full question-id list in the desired order."""

    question_ids: list[uuid.UUID]


class CultureFitQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_index: int
    prompt: str
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
