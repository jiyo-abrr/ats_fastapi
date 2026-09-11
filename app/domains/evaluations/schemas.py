import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.evaluations.dimensions import (
    ASSESSMENT_DIMENSIONS,
    RESUME_DIMENSIONS,
    Rating,
    Recommendation,
)

_KNOWN_RESUME = frozenset(RESUME_DIMENSIONS)
_KNOWN_ASSESSMENT = frozenset(ASSESSMENT_DIMENSIONS)


class EvaluationScoreIn(BaseModel):
    # Bounds mirror application_evaluation_scores column widths.
    dimension: str = Field(min_length=1, max_length=60)
    rating: Rating
    reason: str | None = Field(default=None, max_length=2000)


def _drop_blank_scores(value: object) -> object:
    """Template stubs ship with rating="" — quietly drop unfilled rows rather
    than 422 the whole import."""
    if isinstance(value, list):
        return [
            v
            for v in value
            if not (isinstance(v, dict) and not str(v.get("rating") or "").strip())
        ]
    return value


class ApplicationEvaluationIn(BaseModel):
    application_id: uuid.UUID
    seniority_assessed: str | None = Field(default=None, max_length=50)
    fit_score: int | None = Field(default=None, ge=0, le=100)
    recommendation: Recommendation | None = None
    summary: str | None = Field(default=None, max_length=5000)
    resume_scores: list[EvaluationScoreIn] = Field(default_factory=list)
    assessment_scores: list[EvaluationScoreIn] = Field(default_factory=list)

    @field_validator("seniority_assessed", "summary", "recommendation", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("resume_scores", "assessment_scores", mode="before")
    @classmethod
    def _prune_scores(cls, v: object) -> object:
        return _drop_blank_scores(v)

    @model_validator(mode="after")
    def _check_dimensions(self) -> "ApplicationEvaluationIn":
        # Unknown dimension strings are allowed (analytics groups on whatever is
        # there — see dimensions.py), but a dimension that is *known* to belong
        # to the other category is a mistake, and no dimension may repeat within
        # a category.
        for scores, wrong_category, wrong_names in (
            (self.resume_scores, "assessment", _KNOWN_ASSESSMENT),
            (self.assessment_scores, "resume", _KNOWN_RESUME),
        ):
            seen: set[str] = set()
            for score in scores:
                if score.dimension in seen:
                    raise ValueError(
                        f"dimension '{score.dimension}' appears more than once"
                    )
                seen.add(score.dimension)
                if score.dimension in wrong_names:
                    raise ValueError(
                        f"'{score.dimension}' is a {wrong_category} dimension, "
                        "not valid here"
                    )
        return self


class EvaluationImportIn(BaseModel):
    job_post_id: uuid.UUID
    model: str | None = None
    rubric_version: str | None = None
    evaluations: list[ApplicationEvaluationIn]

    @field_validator("evaluations")
    @classmethod
    def _one_row_per_application(
        cls, v: list[ApplicationEvaluationIn]
    ) -> list[ApplicationEvaluationIn]:
        seen: set[uuid.UUID] = set()
        for item in v:
            if item.application_id in seen:
                raise ValueError(
                    f"application '{item.application_id}' appears more than "
                    "once in this import"
                )
            seen.add(item.application_id)
        return v


class EvaluationImportResultOut(BaseModel):
    imported: int
    skipped: list[str] = Field(default_factory=list)


class EvaluationScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    dimension: str
    rating: str
    reason: str | None


class ApplicationEvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    recommendation: str | None
    fit_score: int | None
    seniority_assessed: str | None
    summary: str | None
    model: str | None
    rubric_version: str | None
    created_at: datetime
    scores: list[EvaluationScoreOut] = Field(default_factory=list)


class JobEvaluationRowOut(BaseModel):
    """One applicant's latest AI evaluation, for the Compare tab's
    side-by-side evaluation matrix."""

    application_id: uuid.UUID
    applicant_first_name: str
    applicant_last_name: str
    applicant_email: str
    evaluation: ApplicationEvaluationOut | None = None


class EvaluationExportJobOut(BaseModel):
    """Status of a background evaluation-pack export (review F09/F26). Poll
    `GET /applications/export-jobs/{id}` until `status` is `done` or `failed`,
    then `GET .../download`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_post_id: uuid.UUID
    status: str
    status_filter: str | None
    error_message: str | None
    created_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
