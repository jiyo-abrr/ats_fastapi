"""Plain-dataclass entities for the import/read side of `evaluations/`
(review F07). `pack.py` (the export ZIP builder) and `export_jobs.py` (the
background-export tracker, which already had its own entity/repository
before this) are untouched — this covers `ApplicationEvaluation` +
`ApplicationEvaluationScore` only.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EvaluationScore:
    id: uuid.UUID
    evaluation_id: uuid.UUID
    category: str
    dimension: str
    rating: str
    reason: str | None = None


@dataclass
class ApplicationEvaluation:
    id: uuid.UUID
    application_id: uuid.UUID
    imported_by_user_id: uuid.UUID
    recommendation: str | None = None
    fit_score: int | None = None
    seniority_assessed: str | None = None
    summary: str | None = None
    model: str | None = None
    rubric_version: str | None = None
    created_at: datetime | None = None
    scores: list[EvaluationScore] = field(default_factory=list)
