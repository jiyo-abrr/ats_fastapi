import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"


@dataclass
class TokenPayload:
    user_id: uuid.UUID
    jti: str
    expires_at: datetime


# bcrypt hard-rejects inputs longer than 72 bytes (it does not silently
# truncate). Callers validate against this and surface a client error rather
# than letting bcrypt raise mid-request. Multibyte characters count for more
# than one byte, so this is a byte budget, not a character count.
MAX_PASSWORD_BYTES = 72


def password_exceeds_max_length(password: str) -> bool:
    return len(password.encode("utf-8")) > MAX_PASSWORD_BYTES


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if password_exceeds_max_length(password):
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _create_token(
    user_id: uuid.UUID,
    token_type: Literal["access", "refresh"],
    expires_delta: timedelta,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: uuid.UUID) -> str:
    return _create_token(
        user_id, "access", timedelta(minutes=settings.jwt_access_expire_minutes)
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    return _create_token(
        user_id, "refresh", timedelta(days=settings.jwt_refresh_expire_days)
    )


def decode_token(
    token: str, expected_type: Literal["access", "refresh"]
) -> TokenPayload:
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected a {expected_type} token")
    return TokenPayload(
        user_id=uuid.UUID(payload["sub"]),
        jti=payload["jti"],
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )
