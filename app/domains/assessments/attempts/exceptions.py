from app.core.exceptions import NotFoundError, ValidationError


class AssessmentAttemptNotFoundError(NotFoundError):
    pass


class AssessmentAttemptExpiredError(ValidationError):
    pass


class AssessmentAttemptAlreadyCompletedError(ValidationError):
    pass


class NotCurrentQuestionError(ValidationError):
    pass


class InvalidAnswerValueError(ValidationError):
    pass


class InvalidAssessmentAttemptReopenError(ValidationError):
    pass
