import uuid

from fastapi import APIRouter, Depends, status

from app.domains.company_addresses.dependencies import get_company_address_service
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
def create_company_address(
    payload: CompanyAddressCreate,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> CompanyAddressOut:
    return service.create(**payload.model_dump())


@router.get("", response_model=list[CompanyAddressOut])
def list_company_addresses(
    service: CompanyAddressService = Depends(get_company_address_service),
) -> list[CompanyAddressOut]:
    return service.list()


@router.get("/{address_id}", response_model=CompanyAddressOut)
def get_company_address(
    address_id: uuid.UUID,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> CompanyAddressOut:
    return service.get(address_id)


@router.put(
    "/{address_id}", response_model=CompanyAddressOut, dependencies=[_manage_jobs]
)
def update_company_address(
    address_id: uuid.UUID,
    payload: CompanyAddressUpdate,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> CompanyAddressOut:
    return service.update(address_id, **payload.model_dump())


@router.delete(
    "/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_manage_jobs],
)
def delete_company_address(
    address_id: uuid.UUID,
    service: CompanyAddressService = Depends(get_company_address_service),
) -> None:
    service.delete(address_id)
