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
class SnapshotQuestion:
    """A question exactly as it read at attempt-issuance time. Same attribute
    surface as PreAssessmentQuestion/CultureFitQuestion/TechnicalAssessmentQuestion
    (order_index/prompt/question_type/config/time_limit_seconds) so the service
    can treat a snapshot and a live template interchangeably."""

    id: uuid.UUID
    order_index: int
    prompt: str
    question_type: str
    config: dict | None = None
    time_limit_seconds: int | None = None


@dataclass
class TemplateSnapshot:
    """A frozen copy of the template (title/instructions/timer/questions) taken
    when the attempt was created (`create_attempts_for_application`). Reads and
    validation use this instead of re-fetching the live template, so an HR edit
    to the template after issuance can't change what an already-answered
    question looked like or silently shift a timer mid-attempt (review F04 /
    docs/decisions/D03). Same attribute surface as a live template entity
    (title/instructions/time_limit_minutes/questions)."""

    title: str
    instructions: str | None
    time_limit_minutes: int | None
    questions: list[SnapshotQuestion] = field(default_factory=list)

    def to_json(self) -> dict:
        """JSON-safe form for the `template_snapshot` JSONB column."""
        return {
            "title": self.title,
            "instructions": self.instructions,
            "time_limit_minutes": self.time_limit_minutes,
            "questions": [
                {
                    "id": str(q.id),
                    "order_index": q.order_index,
                    "prompt": q.prompt,
                    "question_type": q.question_type,
                    "config": q.config,
                    "time_limit_seconds": q.time_limit_seconds,
                }
                for q in self.questions
            ],
        }

    @classmethod
    def from_json(cls, data: dict | None) -> "TemplateSnapshot | None":
        if data is None:
            return None
        return cls(
            title=data["title"],
            instructions=data.get("instructions"),
            time_limit_minutes=data.get("time_limit_minutes"),
            questions=[
                SnapshotQuestion(
                    id=uuid.UUID(q["id"]),
                    order_index=q["order_index"],
                    prompt=q["prompt"],
                    question_type=q["question_type"],
                    config=q.get("config"),
                    time_limit_seconds=q.get("time_limit_seconds"),
                )
                for q in data.get("questions", [])
            ],
        )

    @classmethod
    def from_template(cls, template) -> "TemplateSnapshot":
        """Build a snapshot from a live template entity (Pre/CultureFit/
        Technical — they share this attribute shape) at attempt-issuance time."""
        return cls(
            title=template.title,
            instructions=template.instructions,
            time_limit_minutes=template.time_limit_minutes,
            questions=[
                SnapshotQuestion(
                    id=q.id,
                    order_index=q.order_index,
                    prompt=q.prompt,
                    question_type=q.question_type,
                    config=q.config,
                    time_limit_seconds=q.time_limit_seconds,
                )
                for q in template.questions
            ],
        )


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
    # None only for attempts created before this snapshot existed (the service
    # falls back to a live template fetch for those — see _get_template).
    template_snapshot: TemplateSnapshot | None = None


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
