import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domains.jobs.enums import EmploymentType, JobPostStatus


class CompanyAddressCreate(BaseModel):
    label: str
    line1: str
    line2: str | None = None
    city: str
    state_province: str | None = None
    postal_code: str | None = None
    country: str
    latitude: Decimal | None = None
    longitude: Decimal | None = None


class CompanyAddressUpdate(CompanyAddressCreate):
    pass


class CompanyAddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    line1: str
    line2: str | None
    city: str
    state_province: str | None
    postal_code: str | None
    country: str
    latitude: Decimal | None
    longitude: Decimal | None
    created_at: datetime
    updated_at: datetime


class PositionCreate(BaseModel):
    title: str
    description: str | None = None


class PositionUpdate(PositionCreate):
    pass


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class TagCreate(BaseModel):
    name: str
    description: str | None = None


class TagUpdate(TagCreate):
    pass


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None


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
    tags: list[TagOut]
    excluded_job_post_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime
