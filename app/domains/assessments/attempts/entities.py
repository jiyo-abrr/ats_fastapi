import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# NOTE: `Any` is used for the template-question below because an attempt is
# polymorphic over the 3 independent template domains (see service._get_template)
# — there is no single question type to import here.


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
    # Set by AssessmentService (not the repository) when an attempt is returned
    # to a router — the count comes from the attempt's template, which lives in
    # one of 3 other domains. 0 on the raw repo entity (scheduler paths).
    total_questions: int = 0


@dataclass
class AttemptDetail:
    """Applicant-facing view for taking an attempt: the attempt plus just the
    *current* question (never the full question list — that would defeat the
    strictly-sequential, one-question-at-a-time rule the service enforces)."""

    attempt: AssessmentAttempt
    template_title: str
    template_instructions: str | None
    time_limit_minutes: int | None
    total_questions: int
    answered_count: int
    current_question: Any | None
    current_answer: AssessmentAnswer | None
