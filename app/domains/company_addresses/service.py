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

    async def create(
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
        await self.addresses.add(
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
        await self.uow.commit()
        return await self.addresses.get_by_id(address_id)

    async def get(self, address_id: uuid.UUID) -> entities.CompanyAddress:
        address = await self.addresses.get_by_id(address_id)
        if address is None:
            raise CompanyAddressNotFoundError(
                f"Company address '{address_id}' not found"
            )
        return address

    async def list(self) -> list[entities.CompanyAddress]:
        return await self.addresses.list_all()

    async def update(
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
        await self.get(address_id)
        await self.addresses.update(
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
        await self.uow.commit()
        return await self.addresses.get_by_id(address_id)

    async def delete(self, address_id: uuid.UUID) -> None:
        await self.get(address_id)
        await self.addresses.delete(address_id)
        try:
            await self.uow.commit()
        except IntegrityError:
            await self.uow.rollback()
            raise CompanyAddressInUseError(
                f"Company address '{address_id}' is still referenced by one or "
                "more job posts"
            ) from None
