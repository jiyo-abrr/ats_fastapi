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

    @property
    def full_address(self) -> str:
        parts = [
            self.line1,
            self.line2,
            self.city,
            self.state_province,
            self.postal_code,
            self.country,
        ]
        return ", ".join(p for p in parts if p)
