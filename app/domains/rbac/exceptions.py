from app.core.exceptions import ForbiddenError, NotFoundError


class PermissionDeniedError(ForbiddenError):
    pass


class RoleNotFoundError(NotFoundError):
    pass


class PermissionNotFoundError(NotFoundError):
    pass
