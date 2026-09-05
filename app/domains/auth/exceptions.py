from app.core.exceptions import ConflictError, UnauthorizedError, ValidationError


class EmailAlreadyRegisteredError(ConflictError):
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


class ResumeTooLargeError(ValidationError):
    pass
