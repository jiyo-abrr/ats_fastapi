import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.question_types import QuestionType


class CultureFitTemplate(Base):
    __tablename__ = "culture_fit_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    instructions: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # Overall timer for the whole assessment (layer 2) — starts when the
    # applicant opens the first question of an attempt against this template.
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CultureFitQuestion(Base):
    __tablename__ = "culture_fit_questions"
    __table_args__ = (
        CheckConstraint(
            "question_type IN ("
            + ", ".join(f"'{t.value}'" for t in QuestionType)
            + ")",
            name="ck_culture_fit_questions_question_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("culture_fit_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(String(2000), nullable=False)
    instructions: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Shape depends on question_type — see app.core.question_types. Always
    # read/written as a whole unit, never filtered into individually, so
    # JSONB fits even in this normalized schema.
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Per-question timer (layer 3) — this is where it matters most: culture-
    # fit questions are the ones meant to be individually timed.
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
