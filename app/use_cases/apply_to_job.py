"""`apply_to_job` — the one business operation that spans applications and
assessments, given a single transaction owner.

`POST /applications` must create the application row *and* one assessment
attempt per template the job post has attached, atomically. Previously the
router called `ApplicationService.create()` (which committed) and then
`AssessmentService.create_attempts_for_application()` (which committed
separately); if the second failed, the application persisted with no attempts,
`is_application_fully_assessed()` treated it as vacuously complete, and there
was no retry path (the unique index blocks re-applying).

This use case stages both in one transaction and commits once. Neither domain
service imports the other — the same one-way-dependency reason the schedulers
are composition roots (`assessments` already depends on `applications`).
"""

import uuid

from sqlalchemy.exc import IntegrityError

from app.core.db_errors import violated_constraint
from app.core.unit_of_work import UnitOfWork
from app.domains.applications import entities
from app.domains.applications.exceptions import DuplicateApplicationError
from app.domains.applications.service import (
    _ACTIVE_APPLICATION_INDEX,
    ApplicationService,
)
from app.domains.assessments.attempts.service import AssessmentService
from app.domains.auth import entities as auth_entities


class ApplyToJob:
    def __init__(
        self,
        applications: ApplicationService,
        assessments: AssessmentService,
        uow: UnitOfWork,
    ):
        self.applications = applications
        self.assessments = assessments
        self.uow = uow

    async def execute(
        self, *, job_post_id: uuid.UUID, current_user: auth_entities.User
    ) -> entities.Application:
        """Stage the application + its assessment attempts and commit once.

        The use case owns the transaction: on *any* failure it rolls back
        before propagating, so it is safe to call outside a FastAPI request
        (e.g. a script) as well as inside one.
        """
        try:
            # create(commit=False) flushes — so the application row exists for
            # the attempts' FK, and the duplicate-active-application unique
            # index is caught now rather than at the shared commit.
            application = await self.applications.create(
                job_post_id=job_post_id, current_user=current_user, commit=False
            )
            await self.assessments.create_attempts_for_application(
                application.id, job_post_id, commit=False
            )
            await self.uow.commit()
        except IntegrityError as exc:
            await self.uow.rollback()
            # `create(commit=False)` normally translates the duplicate case
            # already; if it surfaces at the shared commit, translate it —
            # but never report an *unrelated* constraint as a duplicate.
            if violated_constraint(exc) == _ACTIVE_APPLICATION_INDEX:
                raise DuplicateApplicationError(
                    f"You already have an active application for job post "
                    f"'{job_post_id}'"
                ) from None
            raise
        except Exception:
            await self.uow.rollback()
            raise
        return application
