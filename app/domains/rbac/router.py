from fastapi import APIRouter, Depends, status

from app.domains.rbac.dependencies import get_rbac_service, require_permission
from app.domains.rbac.schemas import PermissionOut, RoleOut
from app.domains.rbac.service import RBACService

router = APIRouter(
    prefix="/rbac",
    tags=["rbac"],
    dependencies=[Depends(require_permission("manage_rbac"))],
)


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    rbac_service: RBACService = Depends(get_rbac_service),
) -> list[RoleOut]:
    return await rbac_service.list_roles()


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(
    rbac_service: RBACService = Depends(get_rbac_service),
) -> list[PermissionOut]:
    return await rbac_service.list_permissions()


@router.post(
    "/roles/{role_name}/permissions/{permission_key}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def grant_permission(
    role_name: str,
    permission_key: str,
    rbac_service: RBACService = Depends(get_rbac_service),
) -> None:
    await rbac_service.grant(role_name, permission_key)


@router.delete(
    "/roles/{role_name}/permissions/{permission_key}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_permission(
    role_name: str,
    permission_key: str,
    rbac_service: RBACService = Depends(get_rbac_service),
) -> None:
    await rbac_service.revoke(role_name, permission_key)
