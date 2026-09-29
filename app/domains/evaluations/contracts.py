"""Validated evaluation import commands and results for any application caller."""

import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

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
    # Standardized "City, Province" / "Remote" — see dimensions.LOCATION_FORMAT_HINT.
    location: str | None = Field(default=None, max_length=120)
    fit_score: int | None = Field(default=None, ge=0, le=100)
    recommendation: Recommendation | None = None
    summary: str | None = Field(default=None, max_length=5000)
    resume_scores: list[EvaluationScoreIn] = Field(default_factory=list)
    assessment_scores: list[EvaluationScoreIn] = Field(default_factory=list)

    @field_validator(
        "seniority_assessed", "location", "summary", "recommendation", mode="before"
    )
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
