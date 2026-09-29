"""Change pipeline status and provision interview booking in one transaction."""

import uuid

from app.core.unit_of_work import UnitOfWork
from app.domains.applications.entities import Application
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.service import ApplicationService
from app.domains.auth.entities import User
from app.domains.interviews.scheduling_service import InterviewService


class TransitionApplication:
    def __init__(
        self,
        applications: ApplicationService,
        interviews: InterviewService,
        uow: UnitOfWork,
    ):
        self.applications = applications
        self.interviews = interviews
        self.uow = uow

    async def execute(
        self,
        *,
        application_id: uuid.UUID,
        status: ApplicationStatus,
        hr_assessed: bool,
        current_user: User,
    ) -> Application:
        try:
            result = await self.applications.update_status(
                application_id, status, hr_assessed=hr_assessed, commit=False
            )
            if status == ApplicationStatus.INTERVIEW:
                await self.interviews.ensure_default_request(
                    application_id,
                    created_by_user_id=current_user.id,
                    commit=False,
                )
                config = await self.interviews.get_config()
                await self.applications.set_interview_booking_deadline_for_transition(
                    application_id,
                    default_days=config.interview_booking_days,
                    commit=False,
                )
                result = await self.applications.get(application_id, current_user)
            await self.uow.commit()
        except Exception:
            await self.uow.rollback()
            raise
        return result
