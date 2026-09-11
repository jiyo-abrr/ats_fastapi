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


class ParentApplicationNotAcceptingAssessmentsError(ValidationError):
    """The attempt's parent application is in a state (withdrawn, denied,
    disqualified, or already decided) where its assessments can no longer be
    answered. Historical results stay readable; only continuing is blocked."""


class AssessmentDeadlinePassedError(ValidationError):
    """The parent application's outer assessment deadline has passed and has
    not been extended."""


class MissingAssessmentTemplateError(NotFoundError):
    """The attempt's referenced template (or one of its questions) no longer
    exists — it was edited or deleted after the attempt was created. There is
    no DB FK across this boundary (polymorphic template_id), so this is caught
    at the application layer instead of surfacing as an AttributeError."""
