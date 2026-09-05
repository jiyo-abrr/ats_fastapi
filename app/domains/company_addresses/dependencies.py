from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.company_addresses.repository import CompanyAddressRepository
from app.domains.company_addresses.service import CompanyAddressService


def get_company_address_repository(
    db: Session = Depends(get_db),
) -> CompanyAddressRepository:
    return CompanyAddressRepository(db)


def get_company_address_service(
    addresses: CompanyAddressRepository = Depends(get_company_address_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> CompanyAddressService:
    return CompanyAddressService(addresses, uow)
