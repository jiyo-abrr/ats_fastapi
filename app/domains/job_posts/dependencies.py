from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.company_addresses.dependencies import get_company_address_repository
from app.domains.company_addresses.repository import CompanyAddressRepository
from app.domains.culture_fit_templates.dependencies import (
    get_culture_fit_template_repository,
)
from app.domains.culture_fit_templates.repository import CultureFitTemplateRepository
from app.domains.job_posts.repository import JobPostRepository
from app.domains.job_posts.service import JobPostService
from app.domains.positions.dependencies import get_position_repository
from app.domains.positions.repository import PositionRepository
from app.domains.pre_assessment_templates.dependencies import (
    get_pre_assessment_template_repository,
)
from app.domains.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)
from app.domains.tags.dependencies import get_tag_repository
from app.domains.tags.repository import TagRepository
from app.domains.technical_assessment_templates.dependencies import (
    get_technical_assessment_template_repository,
)
from app.domains.technical_assessment_templates.repository import (
    TechnicalAssessmentTemplateRepository,
)


def get_job_post_repository(db: AsyncSession = Depends(get_db)) -> JobPostRepository:
    return JobPostRepository(db)


def get_job_post_service(
    job_posts: JobPostRepository = Depends(get_job_post_repository),
    positions: PositionRepository = Depends(get_position_repository),
    addresses: CompanyAddressRepository = Depends(get_company_address_repository),
    tags: TagRepository = Depends(get_tag_repository),
    pre_assessment_templates: PreAssessmentTemplateRepository = Depends(
        get_pre_assessment_template_repository
    ),
    culture_fit_templates: CultureFitTemplateRepository = Depends(
        get_culture_fit_template_repository
    ),
    technical_assessment_templates: TechnicalAssessmentTemplateRepository = Depends(
        get_technical_assessment_template_repository
    ),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> JobPostService:
    return JobPostService(
        job_posts,
        positions,
        addresses,
        tags,
        pre_assessment_templates,
        culture_fit_templates,
        technical_assessment_templates,
        uow,
    )
