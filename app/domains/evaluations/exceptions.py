from app.core.exceptions import NotFoundError, ValidationError


class EvaluationNotFoundError(NotFoundError):
    """No AI evaluation has been imported for the application."""


class EmptyEvaluationImportError(ValidationError):
    """The import payload contained no evaluations."""
