import uuid

from app.core.repository import BaseRepository
from app.domains.auth.models import RevokedRefreshToken, User


class UserRepository(BaseRepository[User, uuid.UUID]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()


class RevokedRefreshTokenRepository(BaseRepository[RevokedRefreshToken, str]):
    model = RevokedRefreshToken

    def is_revoked(self, jti: str) -> bool:
        return self.get_by_id(jti) is not None
