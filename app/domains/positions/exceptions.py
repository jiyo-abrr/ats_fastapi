from app.core.exceptions import ConflictError, NotFoundError


class PositionNotFoundError(NotFoundError):
    pass


class PositionInUseError(ConflictError):
    pass
