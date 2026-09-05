from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.domains.auth.dependencies import get_auth_service, get_current_user
from app.domains.auth.models import User
from app.domains.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    SignupResponse,
    TokenResponse,
    UserOut,
)
from app.domains.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED
)
async def signup(
    first_name: str = Form(...),
    middle_initial: str | None = Form(None),
    last_name: str = Form(...),
    contact_number: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    resume: UploadFile = File(...),
    auth_service: AuthService = Depends(get_auth_service),
) -> SignupResponse:
    return await auth_service.signup(
        first_name=first_name,
        middle_initial=middle_initial,
        last_name=last_name,
        contact_number=contact_number,
        email=email,
        password=password,
        resume=resume,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, auth_service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    return auth_service.login(payload.email, payload.password)


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(
    payload: RefreshRequest, auth_service: AuthService = Depends(get_auth_service)
) -> AccessTokenResponse:
    return auth_service.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: RefreshRequest, auth_service: AuthService = Depends(get_auth_service)
) -> None:
    auth_service.logout(payload.refresh_token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
