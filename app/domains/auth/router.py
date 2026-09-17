import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from fastapi_querybuilder import QueryBuilder
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.http_headers import content_disposition_inline
from app.core.rate_limit import rate_limit
from app.core.uploads import read_upload_bounded
from app.domains.auth import entities
from app.domains.auth.dependencies import (
    get_auth_service,
    get_current_user,
    get_user_repository,
)
from app.domains.auth.models import User as UserModel
from app.domains.auth.repository import UserRepository
from app.domains.auth.schemas import (
    AccessTokenResponse,
    ChangePasswordRequest,
    CreateHrAccountRequest,
    LoginRequest,
    RefreshRequest,
    SignupResponse,
    TokenResponse,
    UserOut,
    UserUpdateRequest,
)
from app.domains.auth.service import MAX_RESUME_SIZE_BYTES, AuthService
from app.domains.rbac.dependencies import require_permission
from app.domains.rbac.models import Role as RoleModel

_manage_hr_accounts = Depends(require_permission("manage_hr_accounts"))

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("signup", limit=5, window_seconds=60))],
)
async def signup(
    first_name: str = Form(..., min_length=1, max_length=100),
    middle_initial: str | None = Form(None, max_length=1),
    last_name: str = Form(..., min_length=1, max_length=100),
    contact_number: str = Form(..., min_length=1, max_length=20),
    email: EmailStr = Form(...),
    password: str = Form(...),
    resume: UploadFile = File(...),
    resume_screening_consent: bool = Form(...),
    data_privacy_consent: bool = Form(...),
    auth_service: AuthService = Depends(get_auth_service),
) -> SignupResponse:
    # Read with a hard cap so an oversized upload can't balloon memory before
    # the service's own size check runs (a little slack over the limit lets the
    # service return its friendlier ResumeTooLargeError for near-misses).
    resume_bytes = await read_upload_bounded(resume, MAX_RESUME_SIZE_BYTES + 65536)
    return await auth_service.signup(
        first_name=first_name,
        middle_initial=middle_initial,
        last_name=last_name,
        contact_number=contact_number,
        email=email,
        password=password,
        resume_filename=resume.filename or "resume",
        resume_content_type=resume.content_type,
        resume_bytes=resume_bytes,
        resume_screening_consent=resume_screening_consent,
        data_privacy_consent=data_privacy_consent,
    )


@router.post(
    "/hr-accounts",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("manage_hr_accounts"))],
)
async def create_hr_account(
    payload: CreateHrAccountRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserOut:
    return await auth_service.create_hr_account(
        first_name=payload.first_name,
        middle_initial=payload.middle_initial,
        last_name=payload.last_name,
        contact_number=payload.contact_number,
        email=payload.email,
        password=payload.password,
    )


@router.get("/users", response_model=Page[UserOut], dependencies=[_manage_hr_accounts])
async def list_users(
    scope: Literal["staff", "applicants"] | None = Query(None),
    query=QueryBuilder(UserModel),
    db: AsyncSession = Depends(get_db),
    repo: UserRepository = Depends(get_user_repository),
) -> Page[UserOut]:
    # Eager-load role so repo.map_many's _to_entity call (obj.role.name)
    # doesn't trigger a MissingGreenlet lazy-load on the paginated rows.
    query = query.options(selectinload(UserModel.role))
    if scope == "staff":
        query = query.join(UserModel.role).where(RoleModel.name.in_(["admin", "hr"]))
    elif scope == "applicants":
        query = query.join(UserModel.role).where(RoleModel.name == "applicant")
    return await apaginate(db, query, transformer=repo.map_many)


@router.get(
    "/users/{user_id}", response_model=UserOut, dependencies=[_manage_hr_accounts]
)
async def get_user(
    user_id: uuid.UUID, auth_service: AuthService = Depends(get_auth_service)
) -> UserOut:
    return await auth_service.get_user(user_id)


@router.put(
    "/users/{user_id}", response_model=UserOut, dependencies=[_manage_hr_accounts]
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserOut:
    return await auth_service.update_user(user_id, **payload.model_dump())


@router.post(
    "/users/{user_id}/deactivate",
    response_model=UserOut,
    dependencies=[_manage_hr_accounts],
)
async def deactivate_user(
    user_id: uuid.UUID, auth_service: AuthService = Depends(get_auth_service)
) -> UserOut:
    return await auth_service.set_applicant_active(user_id, is_active=False)


@router.post(
    "/users/{user_id}/activate",
    response_model=UserOut,
    dependencies=[_manage_hr_accounts],
)
async def activate_user(
    user_id: uuid.UUID, auth_service: AuthService = Depends(get_auth_service)
) -> UserOut:
    return await auth_service.set_applicant_active(user_id, is_active=True)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("login", limit=5, window_seconds=60))],
)
async def login(
    payload: LoginRequest, auth_service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    return await auth_service.login(payload.email, payload.password)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    payload: RefreshRequest, auth_service: AuthService = Depends(get_auth_service)
) -> AccessTokenResponse:
    return await auth_service.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest, auth_service: AuthService = Depends(get_auth_service)
) -> None:
    await auth_service.logout(payload.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(current_user: entities.User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.put("/me", response_model=UserOut)
async def update_me(
    payload: UserUpdateRequest,
    current_user: entities.User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserOut:
    return await auth_service.update_user(current_user.id, **payload.model_dump())


@router.patch(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("change-password", limit=5, window_seconds=60))],
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: entities.User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    await auth_service.change_password(
        current_user.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    # This device's refresh token is revoked so it can't silently refresh
    # past the old password — the current access token still works until it
    # naturally expires, but the next refresh attempt forces a real login.
    if payload.refresh_token:
        await auth_service.logout(payload.refresh_token)


@router.get("/me/resume")
async def my_resume(
    current_user: entities.User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    data, content_type, filename = await auth_service.get_own_resume(current_user)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": content_disposition_inline(filename)},
    )
