import uuid

from sqlalchemy.orm import Session

from app.core.repository import BaseRepository
from app.domains.rbac.models import Permission, Role, RolePermission


class RoleRepository(BaseRepository[Role, uuid.UUID]):
    model = Role

    def get_by_name(self, name: str) -> Role | None:
        return self.db.query(Role).filter(Role.name == name).first()


class PermissionRepository(BaseRepository[Permission, uuid.UUID]):
    model = Permission

    def get_by_key(self, key: str) -> Permission | None:
        return self.db.query(Permission).filter(Permission.key == key).first()


class RolePermissionRepository:
    def __init__(self, db: Session):
        self.db = db

    def has_permission(self, role_id: uuid.UUID, permission_key: str) -> bool:
        return (
            self.db.query(RolePermission)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .filter(RolePermission.role_id == role_id, Permission.key == permission_key)
            .first()
            is not None
        )

    def list_for_role(self, role_id: uuid.UUID) -> list[Permission]:
        return (
            self.db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == role_id)
            .all()
        )

    def grant(self, role_id: uuid.UUID, permission_id: uuid.UUID) -> None:
        if (
            self.db.get(RolePermission, (role_id, permission_id)) is not None
        ):
            return
        self.db.add(RolePermission(role_id=role_id, permission_id=permission_id))

    def revoke(self, role_id: uuid.UUID, permission_id: uuid.UUID) -> None:
        row = self.db.get(RolePermission, (role_id, permission_id))
        if row is not None:
            self.db.delete(row)
