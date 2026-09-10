import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InterviewConfig(Base):
    """Single-row table (id is always 1): the global booking rules for candidate
    self-scheduling. Editable by HR on the /calendar page."""

    __tablename__ = "interview_config"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_interview_config_singleton"),
        CheckConstraint(
            "slot_minutes > 0 AND slot_minutes <= 480",
            name="ck_interview_config_slot_minutes",
        ),
        CheckConstraint(
            "horizon_days >= 1 AND horizon_days <= 120",
            name="ck_interview_config_horizon_days",
        ),
        CheckConstraint(
            "min_notice_hours >= 0 AND min_notice_hours <= 336",
            name="ck_interview_config_min_notice_hours",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    slot_minutes: Mapped[int] = mapped_column(nullable=False, default=45)
    horizon_days: Mapped[int] = mapped_column(nullable=False, default=21)
    min_notice_hours: Mapped[int] = mapped_column(nullable=False, default=12)
    # IANA name; the wall-clock times in InterviewAvailabilityRule are read
    # against this zone when generating concrete slot instants.
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Manila"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InterviewAvailabilityRule(Base):
    """A recurring weekly window candidates may book interviews in. `job_post_id`
    NULL is the global default; a set value is that job post's own windows, which
    replace the global set for its applicants. Times are minutes-from-midnight
    in `InterviewConfig.timezone`."""

    __tablename__ = "interview_availability_rules"
    __table_args__ = (
        CheckConstraint(
            "weekday >= 0 AND weekday <= 6",
            name="ck_interview_availability_rules_weekday",
        ),
        CheckConstraint(
            "start_minute >= 0 AND end_minute <= 1440 AND end_minute > start_minute",
            name="ck_interview_availability_rules_span",
        ),
        Index(
            "ix_interview_availability_rules_job_post_id",
            "job_post_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_post_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        nullable=True,
    )
    weekday: Mapped[int] = mapped_column(nullable=False)  # 0 = Monday
    start_minute: Mapped[int] = mapped_column(nullable=False)
    end_minute: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InterviewDateOverride(Base):
    """A calendar-date exception to the recurring weekly windows. Covers a single
    day or a date range (``start_date``..``end_date`` inclusive). When
    ``is_unavailable`` is true the day is fully blocked (holiday, company event);
    otherwise ``start_minute``/``end_minute`` (minutes-from-midnight in
    ``InterviewConfig.timezone``) replace that day's weekly windows. ``job_post_id``
    NULL is the global scope; only the global scope is edited today."""

    __tablename__ = "interview_date_overrides"
    __table_args__ = (
        CheckConstraint(
            "end_date >= start_date",
            name="ck_interview_date_overrides_range",
        ),
        CheckConstraint(
            "is_unavailable OR ("
            "start_minute IS NOT NULL AND end_minute IS NOT NULL "
            "AND start_minute >= 0 AND end_minute <= 1440 "
            "AND end_minute > start_minute)",
            name="ck_interview_date_overrides_hours",
        ),
        Index(
            "ix_interview_date_overrides_job_post_id",
            "job_post_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_post_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        nullable=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_unavailable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    start_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JobPostInterviewer(Base):
    """Staff listed as interviewers for a job post — shown to HR and the
    candidate, not used in slot generation."""

    __tablename__ = "job_post_interviewers"
    __table_args__ = (
        Index(
            "ux_job_post_interviewers",
            "job_post_id",
            "user_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


class InterviewRequest(Base):
    """HR's interview offer for one application: the logistics (mode, location /
    link, duration) plus a set of candidate time slots. The applicant confirms
    by selecting one slot. One row per application — replacing it re-uses the
    same row. Only meaningful while the application is in `interview`."""

    __tablename__ = "interview_requests"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('video', 'onsite', 'phone')",
            name="ck_interview_requests_mode",
        ),
        CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 480",
            name="ck_interview_requests_duration",
        ),
        Index("ux_interview_requests_application_id", "application_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    location_or_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(nullable=False, default=45)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # True: the candidate self-books from interview availability. False: HR
    # hand-picked the InterviewSlot rows.
    self_scheduled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InterviewSlot(Base):
    """One candidate start time offered on an InterviewRequest. The applicant's
    chosen slot has `selected_at` set — one partial unique index enforces at
    most one selected slot per request, another enforces that no two confirmed
    interviews across the org share a start instant (a booked time is gone for
    everyone)."""

    __tablename__ = "interview_slots"
    __table_args__ = (
        Index("ix_interview_slots_request_id", "request_id"),
        Index(
            "ux_interview_slots_one_selected",
            "request_id",
            unique=True,
            postgresql_where=text("selected_at IS NOT NULL"),
        ),
        Index(
            "ux_interview_slots_booked_time",
            "starts_at",
            unique=True,
            postgresql_where=text("selected_at IS NOT NULL"),
        ),
        Index("ix_interview_slots_starts_at", "starts_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    selected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
