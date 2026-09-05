import uuid

from sqlalchemy.orm import Session

from app.core.repository import BaseRepository
from app.domains.rbac import entities
from app.domains.rbac.models import Permission as PermissionModel
from app.domains.rbac.models import Role as RoleModel
from app.domains.rbac.models import RolePermission


class RoleRepository(BaseRepository[RoleModel, entities.Role, uuid.UUID]):
    model = RoleModel

    def _to_entity(self, obj: RoleModel) -> entities.Role:
        return entities.Role(id=obj.id, name=obj.name, description=obj.description)

    def _to_model(self, entity: entities.Role) -> RoleModel:
        return RoleModel(
            id=entity.id, name=entity.name, description=entity.description
        )

    def get_by_name(self, name: str) -> entities.Role | None:
        obj = self.db.query(RoleModel).filter(RoleModel.name == name).first()
        return self._to_entity(obj) if obj is not None else None


class PermissionRepository(
    BaseRepository[PermissionModel, entities.Permission, uuid.UUID]
):
    model = PermissionModel

    def _to_entity(self, obj: PermissionModel) -> entities.Permission:
        return entities.Permission(id=obj.id, key=obj.key, description=obj.description)

    def _to_model(self, entity: entities.Permission) -> PermissionModel:
        return PermissionModel(
            id=entity.id, key=entity.key, description=entity.description
        )

    def get_by_key(self, key: str) -> entities.Permission | None:
        obj = self.db.query(PermissionModel).filter(PermissionModel.key == key).first()
        return self._to_entity(obj) if obj is not None else None


class RolePermissionRepository:
    def __init__(self, db: Session):
        self.db = db

    def has_permission(self, role_id: uuid.UUID, permission_key: str) -> bool:
        return (
            self.db.query(RolePermission)
            .join(PermissionModel, PermissionModel.id == RolePermission.permission_id)
            .filter(
                RolePermission.role_id == role_id,
                PermissionModel.key == permission_key,
            )
            .first()
            is not None
        )

    def list_for_role(self, role_id: uuid.UUID) -> list[entities.Permission]:
        rows = (
            self.db.query(PermissionModel)
            .join(RolePermission, RolePermission.permission_id == PermissionModel.id)
            .filter(RolePermission.role_id == role_id)
            .all()
        )
        return [
            entities.Permission(id=r.id, key=r.key, description=r.description)
            for r in rows
        ]

    def grant(self, role_id: uuid.UUID, permission_id: uuid.UUID) -> None:
        if self.db.get(RolePermission, (role_id, permission_id)) is not None:
            return
        self.db.add(RolePermission(role_id=role_id, permission_id=permission_id))

    def revoke(self, role_id: uuid.UUID, permission_id: uuid.UUID) -> None:
        row = self.db.get(RolePermission, (role_id, permission_id))
        if row is not None:
            self.db.delete(row)
