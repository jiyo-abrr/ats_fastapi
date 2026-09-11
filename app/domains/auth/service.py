import os
import uuid

import jwt
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.db_errors import violated_constraint
from app.core.security import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    password_exceeds_max_length,
    verify_password,
)
from app.core.storage import upload_object
from app.core.unit_of_work import UnitOfWork
from app.domains.auth import entities
from app.domains.auth.exceptions import (
    AccountDeactivatedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidRoleForActionError,
    PasswordTooLongError,
    ResumeTooLargeError,
    UnsupportedResumeTypeError,
    UserNotFoundError,
)
from app.domains.auth.repository import RevokedRefreshTokenRepository, UserRepository
from app.domains.auth.schemas import (
    AccessTokenResponse,
    SignupResponse,
    TokenResponse,
    UserOut,
)
from app.domains.rbac.repository import RoleRepository

# The unique index on users.email (see auth/models.py — index=True, unique=True).
_EMAIL_UNIQUE_INDEX = "ix_users_email"

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

    async def _commit_translating_email_conflict(self) -> None:
        """Commit; a violation of the users-email unique index becomes
        `EmailAlreadyRegisteredError` (closing the get_by_email/insert race).
        Any *other* integrity failure is re-raised untouched."""
        try:
            await self.uow.commit()
        except IntegrityError as exc:
            await self.uow.rollback()
            if violated_constraint(exc) == _EMAIL_UNIQUE_INDEX:
                raise EmailAlreadyRegisteredError(
                    "Email is already registered"
                ) from None
            raise

    @staticmethod
    def _validate_password(password: str) -> None:
        if password_exceeds_max_length(password):
            raise PasswordTooLongError(
                "Password must be at most 72 bytes long "
                "(shorter for passwords with non-ASCII characters)."
            )

    @staticmethod
    async def _hash_password(password: str) -> str:
        # bcrypt is CPU-bound and synchronous — offload it so a burst of
        # signups/logins doesn't stall the event loop (same treatment MinIO
        # uploads already get).
        return await run_in_threadpool(hash_password, password)

    @staticmethod
    async def _verify_password(password: str, password_hash: str) -> bool:
        return await run_in_threadpool(verify_password, password, password_hash)

    async def _require_role(self, name: str):
        role = await self.roles.get_by_name(name)
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
        resume_filename: str,
        resume_content_type: str | None,
        resume_bytes: bytes,
    ) -> SignupResponse:
        self._validate_password(password)
        if await self.users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError("Email is already registered")

        extension = os.path.splitext(resume_filename)[1].lower()
        if extension not in ALLOWED_RESUME_EXTENSIONS:
            raise UnsupportedResumeTypeError(
                f"Resume must be one of {sorted(ALLOWED_RESUME_EXTENSIONS)}"
            )

        if len(resume_bytes) > MAX_RESUME_SIZE_BYTES:
            max_mb = MAX_RESUME_SIZE_BYTES // (1024 * 1024)
            raise ResumeTooLargeError(f"Resume must be smaller than {max_mb} MB")

        applicant_role = await self._require_role("applicant")

        user_id = uuid.uuid4()
        object_key = f"applicant_resume/{user_id}/{uuid.uuid4()}_{resume_filename}"
        # MinIO's SDK is sync-only — run it in a threadpool so it doesn't block
        # the event loop for the duration of the upload.
        await run_in_threadpool(
            upload_object,
            settings.minio_bucket,
            object_key,
            resume_bytes,
            resume_content_type,
        )

        await self.users.add(
            entities.User(
                id=user_id,
                first_name=first_name,
                middle_initial=middle_initial,
                last_name=last_name,
                contact_number=contact_number,
                email=email,
                password_hash=await self._hash_password(password),
                role_id=applicant_role.id,
                role=applicant_role.name,
                resume_object_key=object_key,
            )
        )
        await self._commit_translating_email_conflict()
        user = await self.users.get_by_id(user_id)

        return SignupResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=UserOut.model_validate(user),
        )

    async def create_hr_account(
        self,
        *,
        first_name: str,
        middle_initial: str | None,
        last_name: str,
        contact_number: str,
        email: str,
        password: str,
    ) -> UserOut:
        self._validate_password(password)
        if await self.users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError("Email is already registered")

        hr_role = await self._require_role("hr")

        user_id = uuid.uuid4()
        await self.users.add(
            entities.User(
                id=user_id,
                first_name=first_name,
                middle_initial=middle_initial,
                last_name=last_name,
                contact_number=contact_number,
                email=email,
                password_hash=await self._hash_password(password),
                role_id=hr_role.id,
                role=hr_role.name,
                resume_object_key=None,
            )
        )
        await self._commit_translating_email_conflict()
        user = await self.users.get_by_id(user_id)

        return UserOut.model_validate(user)

    async def get_user(self, user_id: uuid.UUID) -> UserOut:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User '{user_id}' not found")
        return UserOut.model_validate(user)

    async def update_user(
        self,
        user_id: uuid.UUID,
        *,
        first_name: str,
        middle_initial: str | None,
        last_name: str,
        contact_number: str,
        email: str,
    ) -> UserOut:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User '{user_id}' not found")

        if email != user.email and await self.users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError("Email is already registered")

        user.first_name = first_name
        user.middle_initial = middle_initial
        user.last_name = last_name
        user.contact_number = contact_number
        user.email = email
        await self.users.update(user)
        await self._commit_translating_email_conflict()
        return UserOut.model_validate(await self.users.get_by_id(user_id))

    async def set_applicant_active(
        self, user_id: uuid.UUID, *, is_active: bool
    ) -> UserOut:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User '{user_id}' not found")
        if user.role != "applicant":
            raise InvalidRoleForActionError(
                "Only applicant accounts can be deactivated here"
            )

        await self.users.set_active(user_id, is_active)
        await self.uow.commit()
        return UserOut.model_validate(await self.users.get_by_id(user_id))

    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self.users.get_by_email(email)
        if user is None or not await self._verify_password(
            password, user.password_hash
        ):
            raise InvalidCredentialsError("Invalid email or password")
        if not user.is_active:
            raise AccountDeactivatedError("This account has been deactivated")

        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    async def refresh(self, refresh_token: str) -> AccessTokenResponse:
        token = self._decode_refresh_token(refresh_token)

        if await self.revoked_tokens.is_revoked(token.jti):
            raise InvalidRefreshTokenError("Invalid refresh token")

        user = await self.users.get_by_id(token.user_id)
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError("Invalid refresh token")

        return AccessTokenResponse(access_token=create_access_token(token.user_id))

    async def logout(self, refresh_token: str) -> None:
        token = self._decode_refresh_token(refresh_token)

        if await self.revoked_tokens.is_revoked(token.jti):
            return  # already revoked — logout is idempotent

        await self.revoked_tokens.add(
            entities.RevokedRefreshToken(jti=token.jti, expires_at=token.expires_at)
        )
        await self.uow.commit()

    def _decode_refresh_token(self, refresh_token: str) -> TokenPayload:
        try:
            return decode_token(refresh_token, expected_type="refresh")
        except jwt.InvalidTokenError as exc:
            raise InvalidRefreshTokenError("Invalid refresh token") from exc
