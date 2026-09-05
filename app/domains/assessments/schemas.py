import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SubmitAnswerRequest(BaseModel):
    answer_value: Any


class ReopenAttemptRequest(BaseModel):
    reason: str


class AssessmentAnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_id: uuid.UUID
    question_started_at: datetime
    answered_at: datetime | None
    answer_value: Any | None


class AssessmentAttemptReopenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reopened_by_user_id: uuid.UUID
    reason: str
    reopened_at: datetime | None


class AssessmentAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    template_type: str
    template_id: uuid.UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    answers: list[AssessmentAnswerOut]
    reopens: list[AssessmentAttemptReopenOut]
