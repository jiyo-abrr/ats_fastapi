import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CompanyAddressCreate(BaseModel):
    label: str
    line1: str
    line2: str | None = None
    city: str
    state_province: str | None = None
    postal_code: str | None = None
    country: str
    latitude: Decimal | None = None
    longitude: Decimal | None = None


class CompanyAddressUpdate(CompanyAddressCreate):
    pass


class CompanyAddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    line1: str
    line2: str | None
    city: str
    state_province: str | None
    postal_code: str | None
    country: str
    latitude: Decimal | None
    longitude: Decimal | None
    created_at: datetime
    updated_at: datetime
