import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.applications.enums import ApplicationStatus


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s.value}'" for s in ApplicationStatus) + ")",
            name="ck_applications_status",
        ),
        # One *active* application per applicant per job post — withdrawn
        # applications don't count, so withdrawing frees the slot but a
        # rejected application stays blocking (rejected is terminal).
        Index(
            "ux_applications_active_per_job_post",
            "job_post_id",
            "applicant_id",
            unique=True,
            postgresql_where=text("status != 'withdrawn'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Plain FK columns, no relationship() — job_post/applicant data needed by
    # the list endpoints is composed via explicit projection queries (see
    # ApplicationRepository.list_for_review/list_for_applicant) rather than
    # ORM relationship traversal, since those views only need a few columns
    # from each joined table, not the whole related entity.
    job_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApplicationStatus.APPLIED.value
    )
    # Snapshot of the applicant's resume at the time of applying — deliberately
    # not a live reference to User.resume_object_key, which can change later.
    resume_object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    # Shared deadline covering all 3 required assessments (see the
    # assessments domain) — set at apply-time from the job post's
    # assessment_window_days, extendable per-applicant via
    # ApplicationService.extend_assessment_deadline().
    assessment_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AssessmentDeadlineExtension(Base):
    """Append-only audit log: every time HR extends an application's
    assessment_deadline. Never edited or deleted once written."""

    __tablename__ = "assessment_deadline_extensions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    extended_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    previous_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    new_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    extended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
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
