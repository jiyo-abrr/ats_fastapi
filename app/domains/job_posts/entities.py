import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.domains.tags.entities import Tag


@dataclass
class JobPost:
    id: uuid.UUID
    job_title: str
    description: str
    responsibilities: str
    qualifications: str
    salary_min: Decimal | None
    salary_max: Decimal | None
    employment_type: str
    status: str
    company_address_id: uuid.UUID
    company_address_label: str
    company_address_full: str
    company_address_latitude: Decimal | None
    company_address_longitude: Decimal | None
    position_id: uuid.UUID
    position_title: str
    show_salary: bool = False
    show_tags: bool = False
    currency: str = "PHP"
    assessment_window_days: int = 4
    # NULL = use InterviewConfig.interview_booking_days (the global default).
    interview_booking_days: int | None = None
    # NULL = use InterviewConfig.default_mode (the global default) when
    # scheduling this job post's interviews.
    default_interview_mode: str | None = None
    tags: list[Tag] = field(default_factory=list)
    excluded_job_post_ids: list[uuid.UUID] = field(default_factory=list)
    # At most one of each — enforced by a UniqueConstraint(job_post_id) on
    # each of the 3 join tables, so a single optional id, not a list.
    pre_assessment_template_id: uuid.UUID | None = None
    culture_fit_template_id: uuid.UUID | None = None
    technical_assessment_template_id: uuid.UUID | None = None
    published_at: datetime | None = None
    closed_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
