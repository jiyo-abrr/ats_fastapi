import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.jobs.enums import EmploymentType, JobPostStatus


class CompanyAddress(Base):
    __tablename__ = "company_addresses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state_province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    # Reserved for future geolocation-based search — not used by any query yet.
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class JobPost(Base):
    __tablename__ = "job_posts"
    __table_args__ = (
        CheckConstraint(
            "employment_type IN ("
            + ", ".join(f"'{e.value}'" for e in EmploymentType)
            + ")",
            name="ck_job_posts_employment_type",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s.value}'" for s in JobPostStatus) + ")",
            name="ck_job_posts_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(10000), nullable=False)
    requirements: Mapped[str] = mapped_column(String(10000), nullable=False)
    qualifications: Mapped[str] = mapped_column(String(10000), nullable=False)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=JobPostStatus.DRAFT.value
    )
    company_address_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_addresses.id"), nullable=False
    )
    company_address: Mapped["CompanyAddress"] = relationship()
    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("positions.id"), nullable=False
    )
    position: Mapped["Position"] = relationship()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class JobPostTag(Base):
    __tablename__ = "job_post_tags"

    # job_post_id cascades: a tag association is owned by the job post itself.
    # tag_id stays RESTRICT (default): deleting a Tag still used by a job post
    # must be blocked (TagService.delete catches the IntegrityError as a 409).
    job_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id"), primary_key=True
    )


class JobPostExclusion(Base):
    __tablename__ = "job_post_exclusions"
    __table_args__ = (
        CheckConstraint(
            "job_post_id != excluded_job_post_id",
            name="ck_job_post_exclusion_not_self",
        ),
    )

    # Both sides cascade: if either job post in the pairing is deleted, the
    # exclusion relationship is moot and should disappear, not block deletion.
    job_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    excluded_job_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        primary_key=True,
    )
