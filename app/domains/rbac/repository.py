import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import BaseRepository
from app.domains.rbac import entities
from app.domains.rbac.models import Permission as PermissionModel
from app.domains.rbac.models import Role as RoleModel
from app.domains.rbac.models import RolePermission


class RoleRepository(BaseRepository[RoleModel, entities.Role, uuid.UUID]):
    model = RoleModel

    async def _to_entity(self, obj: RoleModel) -> entities.Role:
        return entities.Role(id=obj.id, name=obj.name, description=obj.description)

    def _to_model(self, entity: entities.Role) -> RoleModel:
        return RoleModel(id=entity.id, name=entity.name, description=entity.description)

    async def get_by_name(self, name: str) -> entities.Role | None:
        result = await self.db.execute(select(RoleModel).where(RoleModel.name == name))
        obj = result.scalar_one_or_none()
        return await self._to_entity(obj) if obj is not None else None


class PermissionRepository(
    BaseRepository[PermissionModel, entities.Permission, uuid.UUID]
):
    model = PermissionModel

    async def _to_entity(self, obj: PermissionModel) -> entities.Permission:
        return entities.Permission(id=obj.id, key=obj.key, description=obj.description)

    def _to_model(self, entity: entities.Permission) -> PermissionModel:
        return PermissionModel(
            id=entity.id, key=entity.key, description=entity.description
        )

    async def get_by_key(self, key: str) -> entities.Permission | None:
        result = await self.db.execute(
            select(PermissionModel).where(PermissionModel.key == key)
        )
        obj = result.scalar_one_or_none()
        return await self._to_entity(obj) if obj is not None else None


class RolePermissionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def has_permission(self, role_id: uuid.UUID, permission_key: str) -> bool:
        result = await self.db.execute(
            select(RolePermission)
            .join(PermissionModel, PermissionModel.id == RolePermission.permission_id)
            .where(
                RolePermission.role_id == role_id,
                PermissionModel.key == permission_key,
            )
        )
        return result.first() is not None

    async def list_for_role(self, role_id: uuid.UUID) -> list[entities.Permission]:
        result = await self.db.execute(
            select(PermissionModel)
            .join(RolePermission, RolePermission.permission_id == PermissionModel.id)
            .where(RolePermission.role_id == role_id)
        )
        return [
            entities.Permission(id=r.id, key=r.key, description=r.description)
            for r in result.scalars().all()
        ]

    async def grant(self, role_id: uuid.UUID, permission_id: uuid.UUID) -> None:
        if await self.db.get(RolePermission, (role_id, permission_id)) is not None:
            return
        self.db.add(RolePermission(role_id=role_id, permission_id=permission_id))

    async def revoke(self, role_id: uuid.UUID, permission_id: uuid.UUID) -> None:
        row = await self.db.get(RolePermission, (role_id, permission_id))
        if row is not None:
            await self.db.delete(row)
