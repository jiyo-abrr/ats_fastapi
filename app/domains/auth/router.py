from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from pydantic import EmailStr

from app.core.rate_limit import rate_limit
from app.domains.auth import entities
from app.domains.auth.dependencies import get_auth_service, get_current_user
from app.domains.auth.schemas import (
    AccessTokenResponse,
    CreateHrAccountRequest,
    LoginRequest,
    RefreshRequest,
    SignupResponse,
    TokenResponse,
    UserOut,
)
from app.domains.auth.service import AuthService
from app.domains.rbac.dependencies import require_permission

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("signup", limit=5, window_seconds=60))],
)
async def signup(
    first_name: str = Form(...),
    middle_initial: str | None = Form(None),
    last_name: str = Form(...),
    contact_number: str = Form(...),
    email: EmailStr = Form(...),
    password: str = Form(...),
    resume: UploadFile = File(...),
    auth_service: AuthService = Depends(get_auth_service),
) -> SignupResponse:
    resume_bytes = await resume.read()
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
