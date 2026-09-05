from collections.abc import Callable, Coroutine

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.auth import entities as auth_entities
from app.domains.auth.dependencies import get_current_user
from app.domains.rbac.exceptions import PermissionDeniedError
from app.domains.rbac.repository import (
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
)
from app.domains.rbac.service import RBACService


def get_role_repository(db: AsyncSession = Depends(get_db)) -> RoleRepository:
    return RoleRepository(db)


def get_permission_repository(
    db: AsyncSession = Depends(get_db),
) -> PermissionRepository:
    return PermissionRepository(db)


def get_role_permission_repository(
    db: AsyncSession = Depends(get_db),
) -> RolePermissionRepository:
    return RolePermissionRepository(db)


def get_rbac_service(
    roles: RoleRepository = Depends(get_role_repository),
    permissions: PermissionRepository = Depends(get_permission_repository),
    role_permissions: RolePermissionRepository = Depends(
        get_role_permission_repository
    ),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> RBACService:
    return RBACService(roles, permissions, role_permissions, uow)


def require_permission(
    permission_key: str,
) -> Callable[..., Coroutine[None, None, None]]:
    async def dependency(
        current_user: auth_entities.User = Depends(get_current_user),
        role_permissions: RolePermissionRepository = Depends(
            get_role_permission_repository
        ),
    ) -> None:
        if not await role_permissions.has_permission(
            current_user.role_id, permission_key
        ):
            raise PermissionDeniedError(
                "You do not have permission to perform this action"
            )

    return dependency
