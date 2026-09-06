import uuid
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from sqlalchemy import Select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.storage import ObjectNotFoundError, get_object
from app.core.unit_of_work import UnitOfWork
from app.domains.applications import entities
from app.domains.applications.enums import (
    ALLOWED_TRANSITIONS,
    WITHDRAWABLE_STATUSES,
    ApplicationStatus,
)
from app.domains.applications.exceptions import (
    ApplicantExcludedError,
    ApplicationNotFoundError,
    DuplicateApplicationError,
    InvalidApplicationStatusTransitionError,
    InvalidAssessmentDeadlineExtensionError,
    JobPostNotAcceptingApplicationsError,
    OnlyApplicantsCanApplyError,
    ResumeUnavailableError,
)
from app.domains.applications.repository import ApplicationRepository
from app.domains.auth import entities as auth_entities
from app.domains.job_posts.enums import JobPostStatus
from app.domains.job_posts.exceptions import JobPostNotFoundError
from app.domains.job_posts.repository import JobPostRepository
from app.domains.rbac.repository import RolePermissionRepository

# The forward-only transition graph (`ALLOWED_TRANSITIONS`) and the
# `WITHDRAWABLE_STATUSES` set both now live in enums.py so schemas can read them
# too (see the `allowed_status_transitions` / `can_withdraw` output fields).

# Statuses extend_assessment_deadline() may act on — applied (the normal
# case, still inside the assessment window) or disqualified (the "revive"
# case: extending the deadline is what un-disqualifies an application, since
# nothing else can move it out of that terminal status).
_DEADLINE_EXTENDABLE_STATUSES = {
    ApplicationStatus.APPLIED,
    ApplicationStatus.DISQUALIFIED,
}


class ApplicationService:
    def __init__(
        self,
        applications: ApplicationRepository,
        job_posts: JobPostRepository,
        role_permissions: RolePermissionRepository,
        uow: UnitOfWork,
    ):
        self.applications = applications
        self.job_posts = job_posts
        self.role_permissions = role_permissions
        self.uow = uow

    async def create(
        self, *, job_post_id: uuid.UUID, current_user: auth_entities.User
    ) -> entities.Application:
        if current_user.role != "applicant":
            raise OnlyApplicantsCanApplyError("Only applicants can apply to job posts")

        job_post = await self.job_posts.get_by_id(job_post_id)
        if job_post is None:
            raise JobPostNotFoundError(f"Job post '{job_post_id}' not found")
        if job_post.status != JobPostStatus.PUBLISHED:
            raise JobPostNotAcceptingApplicationsError(
                f"Job post '{job_post_id}' is not accepting applications"
            )

        for excluded_id in job_post.excluded_job_post_ids:
            if await self.applications.has_any_application_for(
                current_user.id, excluded_id
            ):
                excluded_job_post = await self.job_posts.get_by_id(excluded_id)
                title = (
                    excluded_job_post.job_title
                    if excluded_job_post
                    else excluded_id
                )
                raise ApplicantExcludedError(
                    "You cannot apply to this job post because you previously "
                    f"applied to '{title}'"
                )

        application_id = uuid.uuid4()
        assessment_deadline = datetime.now(UTC) + timedelta(
            days=job_post.assessment_window_days
        )
        await self.applications.add(
            entities.Application(
                id=application_id,
                job_post_id=job_post_id,
                applicant_id=current_user.id,
                status=ApplicationStatus.APPLIED,
                resume_object_key=current_user.resume_object_key,
                assessment_deadline=assessment_deadline,
            )
        )
        try:
            await self.uow.commit()
        except IntegrityError:
            await self.uow.rollback()
            raise DuplicateApplicationError(
                f"You already have an active application for job post '{job_post_id}'"
            ) from None
        return await self.applications.get_by_id(application_id)

    # Thin pass-throughs to the repository's projection queries — kept here
    # (rather than the router calling ApplicationRepository directly) so the
    # router only ever depends on the service, never the repository. The
    # queries themselves stay in the repository; there's no business logic
    # to add here, this is purely a layering boundary.
    async def list_for_review(
        self, *, job_post_id: uuid.UUID | None, status: str | None
    ) -> Select:
        return await self.applications.list_for_review(
            job_post_id=job_post_id, status=status
        )

    async def list_for_applicant(
        self, applicant_id: uuid.UUID, job_post_id: uuid.UUID | None = None
    ) -> Select:
        return await self.applications.list_for_applicant(
            applicant_id, job_post_id=job_post_id
        )

    async def list_deadline_extensions(
        self, application_id: uuid.UUID
    ) -> list[entities.AssessmentDeadlineExtension]:
        return await self.applications.list_deadline_extensions(application_id)

    async def stats(
        self, job_post_id: uuid.UUID | None = None
    ) -> dict[str, object]:
        """Zero-filled status tally for the ATS dashboard (optionally scoped to
        one job post) — replaces the frontend firing one `size=1` list call per
        status and summing client-side."""
        raw = await self.applications.status_counts(job_post_id)
        by_status = {s.value: raw.get(s.value, 0) for s in ApplicationStatus}
        return {"by_status": by_status, "total": sum(by_status.values())}

    async def get_resume(
        self, application_id: uuid.UUID, current_user: auth_entities.User
    ) -> tuple[bytes, str, str]:
        """`(bytes, content_type, filename)` for the application's résumé.
        Reuses get()'s owner-or-manage_applications check (raises 404 for
        anyone else). MinIO is sync — wrapped in a threadpool like the upload."""
        application = await self.get(application_id, current_user)
        try:
            data, content_type = await run_in_threadpool(
                get_object, settings.minio_bucket, application.resume_object_key
            )
        except ObjectNotFoundError as exc:
            raise ResumeUnavailableError(
                "The résumé for this application is not available"
            ) from exc
        filename = PurePosixPath(application.resume_object_key).name or "resume"
        return data, content_type, filename

    async def get(
        self, application_id: uuid.UUID, current_user: auth_entities.User
    ) -> entities.Application:
        application = await self.applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFoundError(f"Application '{application_id}' not found")
        is_owner = application.applicant_id == current_user.id
        if not is_owner and not await self.role_permissions.has_permission(
            current_user.role_id, "manage_applications"
        ):
            # 404, not 403 — don't leak that someone else's application exists.
            raise ApplicationNotFoundError(f"Application '{application_id}' not found")
        return application

    async def withdraw(
        self, application_id: uuid.UUID, current_user: auth_entities.User
    ) -> entities.Application:
        application = await self.applications.get_by_id(application_id)
        if application is None or application.applicant_id != current_user.id:
            raise ApplicationNotFoundError(f"Application '{application_id}' not found")
        if ApplicationStatus(application.status) not in WITHDRAWABLE_STATUSES:
            raise InvalidApplicationStatusTransitionError(
                f"Cannot withdraw an application with status '{application.status}'"
            )
        await self.applications.update_status(
            application_id, ApplicationStatus.WITHDRAWN
        )
        await self.uow.commit()
        return await self.applications.get_by_id(application_id)

    async def update_status(
        self, application_id: uuid.UUID, new_status: ApplicationStatus
    ) -> entities.Application:
        application = await self.applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFoundError(f"Application '{application_id}' not found")
        if new_status in (ApplicationStatus.WITHDRAWN, ApplicationStatus.DISQUALIFIED):
            raise InvalidApplicationStatusTransitionError(
                f"'{new_status}' cannot be set through this endpoint — it is only "
                "reachable via the applicant's own withdraw action or the "
                "automated assessment-deadline sweep"
            )
        current_status = ApplicationStatus(application.status)
        if new_status not in ALLOWED_TRANSITIONS.get(current_status, frozenset()):
            raise InvalidApplicationStatusTransitionError(
                f"Cannot transition application from '{application.status}' to "
                f"'{new_status}'"
            )
        await self.applications.update_status(application_id, new_status)
        await self.uow.commit()
        return await self.applications.get_by_id(application_id)

    async def extend_assessment_deadline(
        self,
        application_id: uuid.UUID,
        *,
        new_deadline: datetime | None,
        extend_by_days: int | None,
        reason: str,
        current_user: auth_entities.User,
    ) -> entities.Application:
        application = await self.applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFoundError(f"Application '{application_id}' not found")
        current_status = ApplicationStatus(application.status)
        if current_status not in _DEADLINE_EXTENDABLE_STATUSES:
            raise InvalidAssessmentDeadlineExtensionError(
                "Cannot extend the assessment deadline for an application with "
                f"status '{application.status}'"
            )

        previous_deadline = application.assessment_deadline or datetime.now(UTC)
        if new_deadline is not None:
            computed_deadline = new_deadline
        else:
            computed_deadline = previous_deadline + timedelta(days=extend_by_days)

        await self.applications.set_assessment_deadline(
            application_id, computed_deadline
        )
        # Extending the deadline on a disqualified application IS the un-
        # disqualify action — nothing else moves it out of that terminal
        # status, since the scheduler only ever disqualifies, never revives.
        if current_status == ApplicationStatus.DISQUALIFIED:
            await self.applications.update_status(
                application_id, ApplicationStatus.APPLIED
            )
        await self.applications.add_deadline_extension(
            entities.AssessmentDeadlineExtension(
                id=uuid.uuid4(),
                application_id=application_id,
                extended_by_user_id=current_user.id,
                reason=reason,
                previous_deadline=previous_deadline,
                new_deadline=computed_deadline,
            )
        )
        await self.uow.commit()
        return await self.applications.get_by_id(application_id)

    async def disqualify(self, application_id: uuid.UUID) -> None:
        """System-only — called from the scheduled disqualification sweep,
        never from a router. Idempotent no-op if the application has already
        moved past `applied` (e.g. a human decided first)."""
        application = await self.applications.get_by_id(application_id)
        if application is None or application.status != ApplicationStatus.APPLIED:
            return
        await self.applications.update_status(
            application_id, ApplicationStatus.DISQUALIFIED
        )
        await self.uow.commit()
