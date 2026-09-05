import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AssessmentAnswer:
    id: uuid.UUID
    attempt_id: uuid.UUID
    question_id: uuid.UUID
    question_started_at: datetime
    answered_at: datetime | None = None
    answer_value: Any | None = None
    superseded_at: datetime | None = None


@dataclass
class AssessmentAttemptReopen:
    id: uuid.UUID
    attempt_id: uuid.UUID
    reopened_by_user_id: uuid.UUID
    reason: str
    reopened_at: datetime | None = None


@dataclass
class AssessmentAttempt:
    id: uuid.UUID
    application_id: uuid.UUID
    template_type: str
    template_id: uuid.UUID
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    answers: list[AssessmentAnswer] = field(default_factory=list)
    reopens: list[AssessmentAttemptReopen] = field(default_factory=list)
