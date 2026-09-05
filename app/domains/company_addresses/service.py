import uuid
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app.core.unit_of_work import UnitOfWork
from app.domains.company_addresses import entities
from app.domains.company_addresses.exceptions import (
    CompanyAddressInUseError,
    CompanyAddressNotFoundError,
)
from app.domains.company_addresses.repository import CompanyAddressRepository


class CompanyAddressService:
    def __init__(self, addresses: CompanyAddressRepository, uow: UnitOfWork):
        self.addresses = addresses
        self.uow = uow

    def create(
        self,
        *,
        label: str,
        line1: str,
        line2: str | None,
        city: str,
        state_province: str | None,
        postal_code: str | None,
        country: str,
        latitude: Decimal | None,
        longitude: Decimal | None,
    ) -> entities.CompanyAddress:
        address_id = uuid.uuid4()
        self.addresses.add(
            entities.CompanyAddress(
                id=address_id,
                label=label,
                line1=line1,
                line2=line2,
                city=city,
                state_province=state_province,
                postal_code=postal_code,
                country=country,
                latitude=latitude,
                longitude=longitude,
            )
        )
        self.uow.commit()
        return self.addresses.get_by_id(address_id)

    def get(self, address_id: uuid.UUID) -> entities.CompanyAddress:
        address = self.addresses.get_by_id(address_id)
        if address is None:
            raise CompanyAddressNotFoundError(
                f"Company address '{address_id}' not found"
            )
        return address

    def list(self) -> list[entities.CompanyAddress]:
        return self.addresses.list_all()

    def update(
        self,
        address_id: uuid.UUID,
        *,
        label: str,
        line1: str,
        line2: str | None,
        city: str,
        state_province: str | None,
        postal_code: str | None,
        country: str,
        latitude: Decimal | None,
        longitude: Decimal | None,
    ) -> entities.CompanyAddress:
        self.get(address_id)
        self.addresses.update(
            entities.CompanyAddress(
                id=address_id,
                label=label,
                line1=line1,
                line2=line2,
                city=city,
                state_province=state_province,
                postal_code=postal_code,
                country=country,
                latitude=latitude,
                longitude=longitude,
            )
        )
        self.uow.commit()
        return self.addresses.get_by_id(address_id)

    def delete(self, address_id: uuid.UUID) -> None:
        self.get(address_id)
        self.addresses.delete(address_id)
        try:
            self.uow.commit()
        except IntegrityError:
            self.uow.rollback()
            raise CompanyAddressInUseError(
                f"Company address '{address_id}' is still referenced by one or "
                "more job posts"
            ) from None
