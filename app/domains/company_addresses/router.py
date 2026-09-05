import uuid

from fastapi import APIRouter, Depends, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from fastapi_querybuilder import QueryBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.company_addresses.dependencies import (
    get_company_address_repository,
    get_company_address_service,
)
from app.domains.company_addresses.models import CompanyAddress as CompanyAddressModel
from app.domains.company_addresses.repository import CompanyAddressRepository
from app.domains.company_addresses.schemas import (
    CompanyAddressCreate,
    CompanyAddressOut,
    CompanyAddressUpdate,
)
from app.domains.company_addresses.service import CompanyAddressService
from app.domains.rbac.dependencies import require_permission

_manage_jobs = Depends(require_permission("manage_jobs"))

router = APIRouter(prefix="/company-addresses", tags=["company-addresses"])


@router.post(
    "",
    response_model=CompanyAddressOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_manage_jobs],
)
async def create_company_address(
    payload: CompanyAddressCreate,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> CompanyAddressOut:
    return await service.create(**payload.model_dump())


@router.get("", response_model=Page[CompanyAddressOut])
async def list_company_addresses(
    query=QueryBuilder(CompanyAddressModel),
    db: AsyncSession = Depends(get_db),
    repo: CompanyAddressRepository = Depends(get_company_address_repository),
) -> Page[CompanyAddressOut]:
    return await apaginate(db, query, transformer=repo.map_many)


@router.get("/{address_id}", response_model=CompanyAddressOut)
async def get_company_address(
    address_id: uuid.UUID,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> CompanyAddressOut:
    return await service.get(address_id)


@router.put(
    "/{address_id}", response_model=CompanyAddressOut, dependencies=[_manage_jobs]
)
async def update_company_address(
    address_id: uuid.UUID,
    payload: CompanyAddressUpdate,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> CompanyAddressOut:
    return await service.update(address_id, **payload.model_dump())


@router.delete(
    "/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_manage_jobs],
)
async def delete_company_address(
    address_id: uuid.UUID,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> None:
    await service.delete(address_id)
