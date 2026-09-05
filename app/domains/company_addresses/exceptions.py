from app.core.exceptions import ConflictError, NotFoundError


class CompanyAddressNotFoundError(NotFoundError):
    pass


class CompanyAddressInUseError(ConflictError):
    pass
