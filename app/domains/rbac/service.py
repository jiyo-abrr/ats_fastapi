from app.core.unit_of_work import UnitOfWork
from app.domains.rbac.exceptions import PermissionNotFoundError, RoleNotFoundError
from app.domains.rbac.repository import (
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
)
from app.domains.rbac.schemas import PermissionOut, RoleOut


class RBACService:
    def __init__(
        self,
        roles: RoleRepository,
        permissions: PermissionRepository,
        role_permissions: RolePermissionRepository,
        uow: UnitOfWork,
    ):
        self.roles = roles
        self.permissions = permissions
        self.role_permissions = role_permissions
        self.uow = uow

    def list_roles(self) -> list[RoleOut]:
        return [
            RoleOut(
                id=role.id,
                name=role.name,
                description=role.description,
                permissions=[
                    PermissionOut.model_validate(p)
                    for p in self.role_permissions.list_for_role(role.id)
                ],
            )
            for role in self.roles.list_all()
        ]

    def list_permissions(self) -> list[PermissionOut]:
        return [PermissionOut.model_validate(p) for p in self.permissions.list_all()]

    def grant(self, role_name: str, permission_key: str) -> None:
        role, permission = self._resolve(role_name, permission_key)
        self.role_permissions.grant(role.id, permission.id)
        self.uow.commit()

    def revoke(self, role_name: str, permission_key: str) -> None:
        role, permission = self._resolve(role_name, permission_key)
        self.role_permissions.revoke(role.id, permission.id)
        self.uow.commit()

    def _resolve(self, role_name: str, permission_key: str):
        role = self.roles.get_by_name(role_name)
        if role is None:
            raise RoleNotFoundError(f"Role '{role_name}' not found")
        permission = self.permissions.get_by_key(permission_key)
        if permission is None:
            raise PermissionNotFoundError(f"Permission '{permission_key}' not found")
        return role, permission
