from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.company_addresses.dependencies import get_company_address_repository
from app.domains.company_addresses.repository import CompanyAddressRepository
from app.domains.job_posts.repository import JobPostRepository
from app.domains.job_posts.service import JobPostService
from app.domains.positions.dependencies import get_position_repository
from app.domains.positions.repository import PositionRepository
from app.domains.tags.dependencies import get_tag_repository
from app.domains.tags.repository import TagRepository


def get_job_post_repository(db: AsyncSession = Depends(get_db)) -> JobPostRepository:
    return JobPostRepository(db)


def get_job_post_service(
    job_posts: JobPostRepository = Depends(get_job_post_repository),
    positions: PositionRepository = Depends(get_position_repository),
    addresses: CompanyAddressRepository = Depends(get_company_address_repository),
    tags: TagRepository = Depends(get_tag_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> JobPostService:
    return JobPostService(job_posts, positions, addresses, tags, uow)
