import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.job_posts.enums import Currency, EmploymentType, JobPostStatus
from app.domains.tags.schemas import TagOut

_Salary = Decimal | None
_ASSESSMENT_WINDOW = Field(default=4, ge=1, le=90)


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
    requirements: str
    qualifications: str
    currency: Currency = Currency.PHP
    employment_type: EmploymentType
    status: JobPostStatus = JobPostStatus.DRAFT
    company_address_id: uuid.UUID
    position_id: uuid.UUID
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    excluded_job_post_ids: list[uuid.UUID] = Field(default_factory=list)
    assessment_window_days: int = _ASSESSMENT_WINDOW
    pre_assessment_template_id: uuid.UUID | None = None
    culture_fit_template_id: uuid.UUID | None = None
    technical_assessment_template_id: uuid.UUID | None = None


class JobPostUpdate(_SalaryRangeMixin):
    job_title: str
    description: str
    requirements: str
    qualifications: str
    currency: Currency = Currency.PHP
    employment_type: EmploymentType
    status: JobPostStatus
    company_address_id: uuid.UUID
    position_id: uuid.UUID
    assessment_window_days: int = _ASSESSMENT_WINDOW


class JobPostStatsOut(BaseModel):
    """GET /job-posts/stats — draft/published/closed tally for the ATS dashboard."""

    by_status: dict[str, int]
    total: int


class JobPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_title: str
    description: str
    requirements: str
    qualifications: str
    salary_min: Decimal | None
    salary_max: Decimal | None
    currency: str
    employment_type: str
    status: str
    company_address_id: uuid.UUID
    company_address_label: str
    position_id: uuid.UUID
    position_title: str
    assessment_window_days: int
    tags: list[TagOut]
    excluded_job_post_ids: list[uuid.UUID]
    pre_assessment_template_id: uuid.UUID | None
    culture_fit_template_id: uuid.UUID | None
    technical_assessment_template_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
