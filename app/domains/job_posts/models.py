import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.company_addresses.models import CompanyAddress
from app.domains.job_posts.enums import EmploymentType, JobPostStatus
from app.domains.positions.models import Position


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
    # How many days an applicant has to complete all required assessments
    # (see the assessments domain) after applying — copied onto
    # Application.assessment_deadline at apply-time.
    assessment_window_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4
    )
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


class JobPostPreAssessmentTemplate(Base):
    __tablename__ = "job_post_pre_assessment_templates"

    # job_post_id is the SOLE primary key (not composite with template_id) —
    # that's what makes "at most one pre-assessment template per job post"
    # structural rather than a separate constraint to maintain.
    job_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # No cascade: deleting a shared, reusable template while it's attached
    # to a job post must be blocked (PreAssessmentTemplateService.delete()
    # catches the IntegrityError as a 409), same as tag_id above. A real FK
    # is possible here (unlike the old single discriminated join table)
    # because this table only ever points at pre_assessment_templates.
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pre_assessment_templates.id"), nullable=False
    )


class JobPostCultureFitTemplate(Base):
    __tablename__ = "job_post_culture_fit_templates"

    job_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("culture_fit_templates.id"), nullable=False
    )


class JobPostTechnicalAssessmentTemplate(Base):
    __tablename__ = "job_post_technical_assessment_templates"

    job_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("technical_assessment_templates.id"),
        nullable=False,
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
