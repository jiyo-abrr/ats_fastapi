from app.core.exceptions import ConflictError, NotFoundError


class CultureFitTemplateNotFoundError(NotFoundError):
    pass


class CultureFitTemplateInUseError(ConflictError):
    pass
