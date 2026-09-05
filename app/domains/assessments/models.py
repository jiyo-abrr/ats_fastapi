import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.assessments.enums import AttemptStatus, TemplateType


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s.value}'" for s in AttemptStatus) + ")",
            name="ck_assessment_attempts_status",
        ),
        CheckConstraint(
            "template_type IN ("
            + ", ".join(f"'{t.value}'" for t in TemplateType)
            + ")",
            name="ck_assessment_attempts_template_type",
        ),
        UniqueConstraint(
            "application_id", "template_type", name="ux_assessment_attempts_unique"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Which of the 3 independent template domains template_id belongs to.
    # No FK on template_id itself — it can't point at one single table since
    # there are 3 possible target tables depending on template_type, and
    # Postgres has no native "FK to one of several tables." Validated at the
    # application layer instead (AssessmentService dispatches by this column).
    template_type: Mapped[str] = mapped_column(String(20), nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AttemptStatus.NOT_STARTED.value
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AssessmentAnswer(Base):
    __tablename__ = "assessment_answers"
    __table_args__ = (
        # Only one *live* (non-superseded) answer per question per attempt —
        # a reopen supersedes the old row instead of deleting it, so the
        # uniqueness constraint has to exclude superseded rows.
        Index(
            "ux_assessment_answers_live_per_question",
            "attempt_id",
            "question_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # No FK — same reasoning as AssessmentAttempt.template_id: which of the 3
    # *_questions tables this points at depends on the parent attempt's
    # template_type, and Postgres can't FK to one of several tables.
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    question_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Shape varies by the question's type — string, bool, number, or a list
    # of strings for multiple_choice. See AssessmentService.validate_answer_value().
    answer_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    # Set by a reopen to soft-invalidate this row without deleting it —
    # the applicant's prior answer stays in the table for the audit trail.
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AssessmentAttemptReopen(Base):
    """Append-only audit log: every time HR reopens an expired attempt.
    Never edited or deleted once written."""

    __tablename__ = "assessment_attempt_reopens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    reopened_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    reopened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
