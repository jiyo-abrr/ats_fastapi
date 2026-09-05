from app.core.exceptions import ConflictError, NotFoundError


class TagNotFoundError(NotFoundError):
    pass


class TagInUseError(ConflictError):
    pass
