import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


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
    # Progress, so the frontend doesn't recompute it from `answers` and doesn't
    # need a (gated) template fetch for the denominator. `total_questions` is
    # populated by AssessmentService when it builds attempts for a router;
    # `answered_count` is derived here from the live answers.
    total_questions: int = 0
    answered_count: int = 0

    @model_validator(mode="after")
    def _fill_answered_count(self):
        self.answered_count = sum(1 for a in self.answers if a.answer_value is not None)
        return self


class CurrentQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_index: int
    prompt: str
    question_type: str
    config: dict | None
    time_limit_seconds: int | None


class AttemptDetailOut(BaseModel):
    """GET /assessment-attempts/{id} — what an applicant needs to render and
    progress through the attempt without a separate (gated) template fetch."""

    id: uuid.UUID
    application_id: uuid.UUID
    template_type: str
    template_id: uuid.UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    template_title: str
    template_instructions: str | None
    time_limit_minutes: int | None
    total_questions: int
    answered_count: int
    current_question: CurrentQuestionOut | None
    current_question_started_at: datetime | None
    current_answer_value: Any | None
