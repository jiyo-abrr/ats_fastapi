import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class CompanyAddress:
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
    created_at: datetime | None = None
    updated_at: datetime | None = None
