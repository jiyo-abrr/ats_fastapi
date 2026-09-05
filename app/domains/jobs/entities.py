import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class CompanyAddress:
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
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Position:
    id: uuid.UUID
    title: str
    description: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Tag:
    id: uuid.UUID
    name: str
    description: str | None = None


@dataclass
class JobPost:
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
    tags: list[Tag] = field(default_factory=list)
    excluded_job_post_ids: list[uuid.UUID] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
