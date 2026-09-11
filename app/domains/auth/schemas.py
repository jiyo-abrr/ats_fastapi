import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Bounds mirror the DB column widths in models.py so an over-long value is a
# 422 at the request boundary, not a database error mid-transaction.
_Name = Annotated[str, Field(min_length=1, max_length=100)]
_MiddleInitial = Annotated[str | None, Field(default=None, max_length=1)]
_ContactNumber = Annotated[str, Field(min_length=1, max_length=20)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    middle_initial: str | None
    last_name: str
    contact_number: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class CreateHrAccountRequest(BaseModel):
    first_name: _Name
    middle_initial: _MiddleInitial
    last_name: _Name
    contact_number: _ContactNumber
    email: EmailStr
    password: str


class UserUpdateRequest(BaseModel):
    first_name: _Name
    middle_initial: _MiddleInitial
    last_name: _Name
    contact_number: _ContactNumber
    email: EmailStr


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SignupResponse(TokenResponse):
    user: UserOut


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
