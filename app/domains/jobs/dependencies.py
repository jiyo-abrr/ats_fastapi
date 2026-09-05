from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.jobs.repository import (
    CompanyAddressRepository,
    JobPostRepository,
    PositionRepository,
    TagRepository,
)
from app.domains.jobs.service import (
    CompanyAddressService,
    JobPostService,
    PositionService,
    TagService,
)


def get_company_address_repository(
    db: Session = Depends(get_db),
) -> CompanyAddressRepository:
    return CompanyAddressRepository(db)


def get_position_repository(db: Session = Depends(get_db)) -> PositionRepository:
    return PositionRepository(db)


def get_tag_repository(db: Session = Depends(get_db)) -> TagRepository:
    return TagRepository(db)


def get_job_post_repository(db: Session = Depends(get_db)) -> JobPostRepository:
    return JobPostRepository(db)


def get_company_address_service(
    addresses: CompanyAddressRepository = Depends(get_company_address_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> CompanyAddressService:
    return CompanyAddressService(addresses, uow)


def get_position_service(
    positions: PositionRepository = Depends(get_position_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PositionService:
    return PositionService(positions, uow)


def get_tag_service(
    tags: TagRepository = Depends(get_tag_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TagService:
    return TagService(tags, uow)


def get_job_post_service(
    job_posts: JobPostRepository = Depends(get_job_post_repository),
    positions: PositionRepository = Depends(get_position_repository),
    addresses: CompanyAddressRepository = Depends(get_company_address_repository),
    tags: TagRepository = Depends(get_tag_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> JobPostService:
    return JobPostService(job_posts, positions, addresses, tags, uow)
