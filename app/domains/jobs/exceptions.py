from app.core.exceptions import ConflictError, NotFoundError


class CompanyAddressNotFoundError(NotFoundError):
    pass


class PositionNotFoundError(NotFoundError):
    pass


class TagNotFoundError(NotFoundError):
    pass


class JobPostNotFoundError(NotFoundError):
    pass


class ResourceInUseError(ConflictError):
    pass
