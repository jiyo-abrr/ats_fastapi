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
    assessment_window_days: int = 4
    tags: list[Tag] = field(default_factory=list)
    excluded_job_post_ids: list[uuid.UUID] = field(default_factory=list)
    # At most one of each — enforced by a UniqueConstraint(job_post_id) on
    # each of the 3 join tables, so a single optional id, not a list.
    pre_assessment_template_id: uuid.UUID | None = None
    culture_fit_template_id: uuid.UUID | None = None
    technical_assessment_template_id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
