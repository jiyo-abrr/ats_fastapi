import os
import uuid

import jwt
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.core.security import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.storage import upload_object
from app.core.unit_of_work import UnitOfWork
from app.domains.auth.models import RevokedRefreshToken, User
from app.domains.auth.repository import RevokedRefreshTokenRepository, UserRepository
from app.domains.auth.schemas import (
    AccessTokenResponse,
    SignupResponse,
    TokenResponse,
    UserOut,
)
from app.domains.rbac.repository import RoleRepository

ALLOWED_RESUME_EXTENSIONS = {".pdf", ".doc", ".docx"}
MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        roles: RoleRepository,
        revoked_tokens: RevokedRefreshTokenRepository,
        uow: UnitOfWork,
    ):
        self.users = users
        self.roles = roles
        self.revoked_tokens = revoked_tokens
        self.uow = uow

    def _require_role(self, name: str):
        role = self.roles.get_by_name(name)
        if role is None:
            raise RuntimeError(f"'{name}' role is not seeded — check migrations")
        return role

    async def signup(
        self,
        *,
        first_name: str,
        middle_initial: str | None,
        last_name: str,
        contact_number: str,
        email: str,
        password: str,
        resume: UploadFile,
    ) -> SignupResponse:
        if self.users.get_by_email(email) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )

        extension = os.path.splitext(resume.filename or "")[1].lower()
        if extension not in ALLOWED_RESUME_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Resume must be one of {sorted(ALLOWED_RESUME_EXTENSIONS)}",
            )

        resume_bytes = await resume.read()
        if len(resume_bytes) > MAX_RESUME_SIZE_BYTES:
            max_mb = MAX_RESUME_SIZE_BYTES // (1024 * 1024)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Resume must be smaller than {max_mb} MB",
            )

        applicant_role = self._require_role("applicant")

        user = User(
            first_name=first_name,
            middle_initial=middle_initial,
            last_name=last_name,
            contact_number=contact_number,
            email=email,
            password_hash=hash_password(password),
            role_id=applicant_role.id,
            resume_object_key="",
        )
        self.users.add(user)
        self.uow.flush()

        object_key = (
            f"applicant_resume/{user.id}/{uuid.uuid4()}_{resume.filename or 'resume'}"
        )
        upload_object(
            settings.minio_bucket, object_key, resume_bytes, resume.content_type
        )
        user.resume_object_key = object_key

        self.uow.commit()
        self.uow.refresh(user)

        return SignupResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=UserOut.model_validate(user),
        )

    def create_hr_account(
        self,
        *,
        first_name: str,
        middle_initial: str | None,
        last_name: str,
        contact_number: str,
        email: str,
        password: str,
    ) -> UserOut:
        if self.users.get_by_email(email) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )

        hr_role = self._require_role("hr")

        user = User(
            first_name=first_name,
            middle_initial=middle_initial,
            last_name=last_name,
            contact_number=contact_number,
            email=email,
            password_hash=hash_password(password),
            role_id=hr_role.id,
            resume_object_key=None,
        )
        self.users.add(user)
        self.uow.commit()
        self.uow.refresh(user)

        return UserOut.model_validate(user)

    def login(self, email: str, password: str) -> TokenResponse:
        user = self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    def refresh(self, refresh_token: str) -> AccessTokenResponse:
        token = self._decode_refresh_token(refresh_token)

        if self.revoked_tokens.is_revoked(token.jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        if self.users.get_by_id(token.user_id) is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        return AccessTokenResponse(access_token=create_access_token(token.user_id))

    def logout(self, refresh_token: str) -> None:
        token = self._decode_refresh_token(refresh_token)

        if self.revoked_tokens.is_revoked(token.jti):
            return  # already revoked — logout is idempotent

        self.revoked_tokens.add(
            RevokedRefreshToken(jti=token.jti, expires_at=token.expires_at)
        )
        self.uow.commit()

    def _decode_refresh_token(self, refresh_token: str) -> TokenPayload:
        try:
            return decode_token(refresh_token, expected_type="refresh")
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            ) from exc
