from app.core.exceptions import ConflictError, NotFoundError, ValidationError


class CultureFitTemplateNotFoundError(NotFoundError):
    pass


class CultureFitTemplateInUseError(ConflictError):
    pass


class CultureFitQuestionNotFoundError(NotFoundError):
    pass


class CultureFitQuestionsReorderError(ValidationError):
    pass
