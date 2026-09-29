"""Authentication results independent of HTTP serialization."""

from dataclasses import dataclass

from app.domains.auth.entities import User


@dataclass(kw_only=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@dataclass(kw_only=True)
class SignupResult(TokenPair):
    user: User


@dataclass
class AccessToken:
    access_token: str
    token_type: str = "bearer"
