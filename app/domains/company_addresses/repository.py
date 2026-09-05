import uuid

from app.core.repository import BaseRepository
from app.domains.company_addresses import entities
from app.domains.company_addresses.models import CompanyAddress as CompanyAddressModel


class CompanyAddressRepository(
    BaseRepository[CompanyAddressModel, entities.CompanyAddress, uuid.UUID]
):
    model = CompanyAddressModel

    def _to_entity(self, obj: CompanyAddressModel) -> entities.CompanyAddress:
        return entities.CompanyAddress(
            id=obj.id,
            label=obj.label,
            line1=obj.line1,
            line2=obj.line2,
            city=obj.city,
            state_province=obj.state_province,
            postal_code=obj.postal_code,
            country=obj.country,
            latitude=obj.latitude,
            longitude=obj.longitude,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    def _to_model(self, entity: entities.CompanyAddress) -> CompanyAddressModel:
        return CompanyAddressModel(
            id=entity.id,
            label=entity.label,
            line1=entity.line1,
            line2=entity.line2,
            city=entity.city,
            state_province=entity.state_province,
            postal_code=entity.postal_code,
            country=entity.country,
            latitude=entity.latitude,
            longitude=entity.longitude,
        )

    def update(self, entity: entities.CompanyAddress) -> None:
        obj = self.db.get(CompanyAddressModel, entity.id)
        if obj is None:
            return
        obj.label = entity.label
        obj.line1 = entity.line1
        obj.line2 = entity.line2
        obj.city = entity.city
        obj.state_province = entity.state_province
        obj.postal_code = entity.postal_code
        obj.country = entity.country
        obj.latitude = entity.latitude
        obj.longitude = entity.longitude
