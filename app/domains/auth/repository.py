import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository
from app.domains.auth import entities
from app.domains.auth.models import RevokedRefreshToken as RevokedRefreshTokenModel
from app.domains.auth.models import User as UserModel


class UserRepository(BaseRepository[UserModel, entities.User, uuid.UUID]):
    model = UserModel

    async def _to_entity(self, obj: UserModel) -> entities.User:
        return entities.User(
            id=obj.id,
            first_name=obj.first_name,
            middle_initial=obj.middle_initial,
            last_name=obj.last_name,
            contact_number=obj.contact_number,
            email=obj.email,
            password_hash=obj.password_hash,
            role_id=obj.role_id,
            role=obj.role.name,
            resume_object_key=obj.resume_object_key,
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    def _to_model(self, entity: entities.User) -> UserModel:
        return UserModel(
            id=entity.id,
            first_name=entity.first_name,
            middle_initial=entity.middle_initial,
            last_name=entity.last_name,
            contact_number=entity.contact_number,
            email=entity.email,
            password_hash=entity.password_hash,
            role_id=entity.role_id,
            resume_object_key=entity.resume_object_key,
        )

    # Overridden: _to_entity accesses obj.role.name — under AsyncSession that
    # attribute must already be loaded (no implicit lazy-load like sync has),
    # so every fetch path here eager-loads the role relationship.
    async def get_by_id(self, id: uuid.UUID) -> entities.User | None:
        result = await self.db.execute(
            select(UserModel)
            .where(UserModel.id == id)
            .options(selectinload(UserModel.role))
        )
        obj = result.scalar_one_or_none()
        return await self._to_entity(obj) if obj is not None else None

    async def list_all(self) -> list[entities.User]:
        result = await self.db.execute(
            select(UserModel).options(selectinload(UserModel.role))
        )
        return [await self._to_entity(obj) for obj in result.scalars().all()]

    async def update(self, entity: entities.User) -> None:
        obj = await self.db.get(UserModel, entity.id)
        if obj is None:
            return
        obj.first_name = entity.first_name
        obj.middle_initial = entity.middle_initial
        obj.last_name = entity.last_name
        obj.contact_number = entity.contact_number
        obj.email = entity.email

    async def set_active(self, id: uuid.UUID, is_active: bool) -> None:
        obj = await self.db.get(UserModel, id)
        if obj is None:
            return
        obj.is_active = is_active

    async def get_by_email(self, email: str) -> entities.User | None:
        result = await self.db.execute(
            select(UserModel)
            .where(UserModel.email == email)
            .options(selectinload(UserModel.role))
        )
        obj = result.scalar_one_or_none()
        return await self._to_entity(obj) if obj is not None else None


class RevokedRefreshTokenRepository(
    BaseRepository[RevokedRefreshTokenModel, entities.RevokedRefreshToken, str]
):
    model = RevokedRefreshTokenModel

    async def _to_entity(
        self, obj: RevokedRefreshTokenModel
    ) -> entities.RevokedRefreshToken:
        return entities.RevokedRefreshToken(
            jti=obj.jti, expires_at=obj.expires_at, revoked_at=obj.revoked_at
        )

    def _to_model(
        self, entity: entities.RevokedRefreshToken
    ) -> RevokedRefreshTokenModel:
        return RevokedRefreshTokenModel(jti=entity.jti, expires_at=entity.expires_at)

    async def is_revoked(self, jti: str) -> bool:
        return await self.get_by_id(jti) is not None

    async def delete_expired(self, now: datetime) -> int:
        """Drop denylist rows whose refresh token has already expired — an
        expired token is rejected on its own merits, so the row is dead weight.
        Returns the number removed."""
        result = await self.db.execute(
            delete(RevokedRefreshTokenModel).where(
                RevokedRefreshTokenModel.expires_at < now
            )
        )
        return result.rowcount or 0
