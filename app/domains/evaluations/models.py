import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EvaluationExportJob(Base):
    """A background evaluation-pack export (review F09/F26) — the pack is
    built by an arq worker (`app/workers/evaluation_export.py`), not inline in
    the request, so a job post with more applicants/résumés than
    `EVALUATION_PACK_MAX`/`EVALUATION_PACK_MAX_BYTES` still gets an export,
    just an asynchronous one. `result_object_key` points into the same MinIO
    bucket resumes use, under the `evaluation_packs/` prefix."""

    __tablename__ = "evaluation_export_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed')",
            name="ck_evaluation_export_jobs_status",
        ),
        Index("ix_evaluation_export_jobs_job_post_id", "job_post_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status_filter: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    result_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ApplicationEvaluation(Base):
    """An external-AI evaluation of one application, imported after an offline
    (ChatGPT) scoring run. One row = one imported run; the newest per
    application is treated as current. Kept as history for analytics."""

    __tablename__ = "application_evaluations"
    __table_args__ = (
        CheckConstraint(
            "recommendation IN ('advance', 'hold', 'reject')",
            name="ck_application_evaluations_recommendation",
        ),
        CheckConstraint(
            "fit_score IS NULL OR (fit_score >= 0 AND fit_score <= 100)",
            name="ck_application_evaluations_fit_score",
        ),
        Index("ix_application_evaluations_application_id", "application_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    imported_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    recommendation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fit_score: Mapped[int | None] = mapped_column(nullable=True)
    seniority_assessed: Mapped[str | None] = mapped_column(String(50), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rubric_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ApplicationEvaluationScore(Base):
    """One dimension of an ApplicationEvaluation (e.g. resume /
    tenure_stability -> qualified). Normalised so analytics can pivot on
    (category, dimension, rating)."""

    __tablename__ = "application_evaluation_scores"
    __table_args__ = (
        CheckConstraint(
            "rating IN ('strong', 'qualified', 'below_bar', 'na')",
            name="ck_application_evaluation_scores_rating",
        ),
        CheckConstraint(
            "category IN ('resume', 'assessment')",
            name="ck_application_evaluation_scores_category",
        ),
        UniqueConstraint(
            "evaluation_id",
            "category",
            "dimension",
            name="uq_application_evaluation_scores_dimension",
        ),
        Index("ix_application_evaluation_scores_evaluation_id", "evaluation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("application_evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    dimension: Mapped[str] = mapped_column(String(60), nullable=False)
    rating: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
