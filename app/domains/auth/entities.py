import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    id: uuid.UUID
    first_name: str
    middle_initial: str | None
    last_name: str
    contact_number: str
    email: str
    password_hash: str
    role_id: uuid.UUID
    role: str
    resume_object_key: str | None
    # When an applicant consented, at signup, to their résumé being used for
    # screening — NULL for HR/admin accounts, which never go through that
    # consent step. Set once, never edited.
    resume_screening_consent_at: datetime | None = None
    # When an applicant consented, at signup, to processing of their personal
    # data under the Data Privacy Act — NULL for HR/admin accounts, same as
    # resume_screening_consent_at above. Set once, never edited.
    data_privacy_consent_at: datetime | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class RevokedRefreshToken:
    jti: str
    expires_at: datetime
    revoked_at: datetime | None = None
