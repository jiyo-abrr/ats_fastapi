import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.interviews.enums import InterviewMode
from app.domains.job_posts.enums import Currency, EmploymentType, JobPostStatus
from app.domains.tags.schemas import TagOut

_Salary = Decimal | None
_ASSESSMENT_WINDOW = Field(default=4, ge=1, le=90)
# NULL = use InterviewConfig.interview_booking_days (the global default).
_INTERVIEW_BOOKING_DAYS = Field(default=None, ge=1, le=120)


class _SalaryRangeMixin(BaseModel):
    salary_min: _Salary = Field(default=None, ge=0)
    salary_max: _Salary = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _salary_order(self):
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("salary_min must not be greater than salary_max")
        return self


class JobPostCreate(_SalaryRangeMixin):
    job_title: str
    description: str
    responsibilities: str
    qualifications: str
    show_salary: bool = False
    show_tags: bool = False
    currency: Currency = Currency.PHP
    employment_type: EmploymentType
    status: JobPostStatus = JobPostStatus.DRAFT
    company_address_id: uuid.UUID
    position_id: uuid.UUID
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    excluded_job_post_ids: list[uuid.UUID] = Field(default_factory=list)
    assessment_window_days: int = _ASSESSMENT_WINDOW
    interview_booking_days: int | None = _INTERVIEW_BOOKING_DAYS
    # NULL = use InterviewConfig.default_mode (the global default).
    default_interview_mode: InterviewMode | None = None
    # HR-set target end date — informational only, independent of when the
    # post is actually closed.
    expires_at: datetime | None = None
    pre_assessment_template_id: uuid.UUID | None = None
    culture_fit_template_id: uuid.UUID | None = None
    technical_assessment_template_id: uuid.UUID | None = None


class JobPostUpdate(_SalaryRangeMixin):
    job_title: str
    description: str
    responsibilities: str
    qualifications: str
    show_salary: bool = False
    show_tags: bool = False
    currency: Currency = Currency.PHP
    employment_type: EmploymentType
    status: JobPostStatus
    company_address_id: uuid.UUID
    position_id: uuid.UUID
    assessment_window_days: int = _ASSESSMENT_WINDOW
    interview_booking_days: int | None = _INTERVIEW_BOOKING_DAYS
    default_interview_mode: InterviewMode | None = None
    expires_at: datetime | None = None


class JobPostStatsOut(BaseModel):
    """GET /job-posts/stats — draft/published/closed tally for the ATS dashboard."""

    by_status: dict[str, int]
    total: int


class JobPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_title: str
    description: str
    responsibilities: str
    qualifications: str
    salary_min: Decimal | None
    salary_max: Decimal | None
    show_salary: bool
    show_tags: bool
    currency: str
    employment_type: str
    status: str
    company_address_id: uuid.UUID
    company_address_label: str
    company_address_full: str
    company_address_latitude: Decimal | None
    company_address_longitude: Decimal | None
    position_id: uuid.UUID
    position_title: str
    assessment_window_days: int
    interview_booking_days: int | None
    default_interview_mode: InterviewMode | None
    tags: list[TagOut]
    excluded_job_post_ids: list[uuid.UUID]
    pre_assessment_template_id: uuid.UUID | None
    culture_fit_template_id: uuid.UUID | None
    technical_assessment_template_id: uuid.UUID | None
    published_at: datetime | None
    closed_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
