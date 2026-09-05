import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.auth.models import User
from app.domains.auth.repository import RevokedRefreshTokenRepository, UserRepository
from app.domains.auth.service import AuthService
from app.domains.rbac.repository import RoleRepository

_bearer_scheme = HTTPBearer()

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


# Duplicated (not imported from rbac.dependencies) to avoid a circular import:
# rbac.dependencies imports get_current_user from this module.
def get_role_repository(db: Session = Depends(get_db)) -> RoleRepository:
    return RoleRepository(db)


def get_revoked_token_repository(
    db: Session = Depends(get_db),
) -> RevokedRefreshTokenRepository:
    return RevokedRefreshTokenRepository(db)


def get_auth_service(
    users: UserRepository = Depends(get_user_repository),
    roles: RoleRepository = Depends(get_role_repository),
    revoked_tokens: RevokedRefreshTokenRepository = Depends(
        get_revoked_token_repository
    ),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> AuthService:
    return AuthService(users, roles, revoked_tokens, uow)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    users: UserRepository = Depends(get_user_repository),
) -> User:
    try:
        token = decode_token(credentials.credentials, expected_type="access")
    except jwt.InvalidTokenError as exc:
        raise _CREDENTIALS_ERROR from exc

    user = users.get_by_id(token.user_id)
    if user is None:
        raise _CREDENTIALS_ERROR
    return user
