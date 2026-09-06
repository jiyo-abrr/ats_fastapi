import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domains.job_posts.enums import EmploymentType, JobPostStatus
from app.domains.tags.schemas import TagOut


class JobPostCreate(BaseModel):
    job_title: str
    description: str
    requirements: str
    qualifications: str
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    employment_type: EmploymentType
    status: JobPostStatus = JobPostStatus.DRAFT
    company_address_id: uuid.UUID
    position_id: uuid.UUID
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    excluded_job_post_ids: list[uuid.UUID] = Field(default_factory=list)
    assessment_window_days: int = 4
    pre_assessment_template_id: uuid.UUID | None = None
    culture_fit_template_id: uuid.UUID | None = None
    technical_assessment_template_id: uuid.UUID | None = None


class JobPostUpdate(BaseModel):
    job_title: str
    description: str
    requirements: str
    qualifications: str
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    employment_type: EmploymentType
    status: JobPostStatus
    company_address_id: uuid.UUID
    position_id: uuid.UUID
    assessment_window_days: int = 4


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
