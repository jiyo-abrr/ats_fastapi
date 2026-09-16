import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GeocodedLocation(Base):
    """Cache of free-text location -> coordinates lookups (see geocoding.py),
    keyed by the normalized query text. analytics otherwise owns no write
    paths (it's a read-only cross-domain reporting layer) — this is the one
    exception, a technical cache for its own use, not domain data any other
    domain reads or writes.

    `latitude`/`longitude` are null when the lookup ran but found nothing —
    still cached, so an unresolvable location (typo, "Remote", etc.) isn't
    re-queried against Nominatim on every dashboard load."""

    __tablename__ = "geocoded_locations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
