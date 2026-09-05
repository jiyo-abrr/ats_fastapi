import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TechnicalAssessmentQuestion:
    id: uuid.UUID
    template_id: uuid.UUID
    order_index: int
    prompt: str
    question_type: str
    instructions: str | None = None
    config: dict | None = None
    time_limit_seconds: int | None = None


@dataclass
class TechnicalAssessmentTemplate:
    id: uuid.UUID
    title: str
    description: str | None
    instructions: str | None
    time_limit_minutes: int | None
    questions: list[TechnicalAssessmentQuestion] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
