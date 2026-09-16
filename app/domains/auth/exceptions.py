from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


class EmailAlreadyRegisteredError(ConflictError):
    pass


class UserNotFoundError(NotFoundError):
    pass


class AccountDeactivatedError(UnauthorizedError):
    pass


class InvalidRoleForActionError(ValidationError):
    pass


class InvalidCredentialsError(UnauthorizedError):
    pass


class InvalidRefreshTokenError(UnauthorizedError):
    pass


class InvalidAccessTokenError(UnauthorizedError):
    def __init__(self, message: str):
        super().__init__(message, headers={"WWW-Authenticate": "Bearer"})


class UnsupportedResumeTypeError(ValidationError):
    pass


class ResumeScreeningConsentRequiredError(ValidationError):
    """Signup didn't check the "use my résumé for screening" box."""


class ResumeTooLargeError(ValidationError):
    pass


class ResumeUnavailableError(NotFoundError):
    pass


class PasswordTooLongError(ValidationError):
    """Password exceeds bcrypt's 72-byte input limit."""


class PasswordTooWeakError(ValidationError):
    """Password doesn't meet the minimum complexity requirement."""
