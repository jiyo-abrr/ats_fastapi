import uuid

from sqlalchemy import Select
from sqlalchemy.exc import IntegrityError

from app.core.unit_of_work import UnitOfWork
from app.domains.applications import entities
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.exceptions import (
    ApplicantExcludedError,
    ApplicationNotFoundError,
    DuplicateApplicationError,
    InvalidApplicationStatusTransitionError,
    JobPostNotAcceptingApplicationsError,
    OnlyApplicantsCanApplyError,
)
from app.domains.applications.repository import ApplicationRepository
from app.domains.auth import entities as auth_entities
from app.domains.job_posts.enums import JobPostStatus
from app.domains.job_posts.exceptions import JobPostNotFoundError
from app.domains.job_posts.repository import JobPostRepository
from app.domains.rbac.repository import RolePermissionRepository

# Forward-only status transitions HR/admin can make. `withdrawn` is reachable
# only via ApplicationService.withdraw() (applicant-only), never through here.
_ALLOWED_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.SUBMITTED: {
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.REJECTED,
    },
    ApplicationStatus.UNDER_REVIEW: {
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.REJECTED,
    },
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
        await self.applications.add(
            entities.Application(
                id=application_id,
                job_post_id=job_post_id,
                applicant_id=current_user.id,
                status=ApplicationStatus.SUBMITTED,
                resume_object_key=current_user.resume_object_key,
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

    async def list_for_applicant(self, applicant_id: uuid.UUID) -> Select:
        return await self.applications.list_for_applicant(applicant_id)

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
        if application.status not in (
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.UNDER_REVIEW,
        ):
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
        if new_status == ApplicationStatus.WITHDRAWN:
            raise InvalidApplicationStatusTransitionError(
                "HR/admin cannot withdraw an application on behalf of an applicant"
            )
        current_status = ApplicationStatus(application.status)
        if new_status not in _ALLOWED_TRANSITIONS.get(current_status, set()):
            raise InvalidApplicationStatusTransitionError(
                f"Cannot transition application from '{application.status}' to "
                f"'{new_status}'"
            )
        await self.applications.update_status(application_id, new_status)
        await self.uow.commit()
        return await self.applications.get_by_id(application_id)
