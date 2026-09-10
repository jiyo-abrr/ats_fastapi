import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status

from app.domains.applications.dependencies import get_application_service
from app.domains.applications.service import ApplicationService
from app.domains.auth import entities as auth_entities
from app.domains.auth.dependencies import get_current_user
from app.domains.interviews.availability_service import InterviewAvailabilityService
from app.domains.interviews.dependencies import (
    get_interview_availability_service,
    get_interview_service,
)
from app.domains.interviews.scheduling_service import InterviewService
from app.domains.interviews.schemas import (
    DateOverrideOut,
    DateOverridesIn,
    GlobalAvailabilityIn,
    GlobalAvailabilityOut,
    InterviewerOut,
    InterviewRequestIn,
    InterviewRequestOut,
    InterviewStatusOut,
    JobPostAvailabilityIn,
    JobPostAvailabilityOut,
    OpenSlotOut,
    SelectSlotIn,
    UpcomingInterviewOut,
)
from app.domains.rbac.dependencies import require_permission

_manage_applications = Depends(require_permission("manage_applications"))

# Interview availability — the recurring weekly windows candidates self-book
# into (global on the /calendar page, or per job post).
availability_router = APIRouter(
    prefix="/interview-availability",
    tags=["interview-availability"],
    dependencies=[_manage_applications],
)

# The per-application interview offer / slot confirmation. Mounted under
# /applications; the owner-or-manage_applications check is reused from
# ApplicationService.get() (a composition-root dependency, not a service link).
interview_router = APIRouter(prefix="/applications", tags=["interviews"])


@availability_router.get("", response_model=GlobalAvailabilityOut)
async def get_global_availability(
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> GlobalAvailabilityOut:
    return await availability.get_global()


@availability_router.put("", response_model=GlobalAvailabilityOut)
async def set_global_availability(
    payload: GlobalAvailabilityIn,
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> GlobalAvailabilityOut:
    return await availability.set_global(payload)


@availability_router.get("/overrides", response_model=list[DateOverrideOut])
async def get_date_overrides(
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> list[DateOverrideOut]:
    return await availability.get_overrides()


@availability_router.put("/overrides", response_model=list[DateOverrideOut])
async def set_date_overrides(
    payload: DateOverridesIn,
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> list[DateOverrideOut]:
    """Whole-list replace of the global date overrides — what the dedicated
    overrides page and its CSV import send."""
    return await availability.set_overrides(payload)


@availability_router.get("/upcoming", response_model=list[UpcomingInterviewOut])
async def upcoming_interviews(
    interviews: InterviewService = Depends(get_interview_service),
) -> list[UpcomingInterviewOut]:
    return await interviews.upcoming()


@availability_router.get("/schedule", response_model=list[UpcomingInterviewOut])
async def interview_schedule(
    start: datetime,
    end: datetime,
    interviews: InterviewService = Depends(get_interview_service),
) -> list[UpcomingInterviewOut]:
    """Confirmed interviews within `[start, end)` — the calendar's visible
    window."""
    return await interviews.schedule(start=start, end=end)


@availability_router.get("/statuses", response_model=list[InterviewStatusOut])
async def job_post_interview_statuses(
    job_post_id: uuid.UUID,
    interviews: InterviewService = Depends(get_interview_service),
) -> list[InterviewStatusOut]:
    return await interviews.statuses_for_job_post(job_post_id)


@availability_router.get("/staff", response_model=list[InterviewerOut])
async def list_interview_staff(
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> list[InterviewerOut]:
    return await availability.list_staff()


@availability_router.get(
    "/job-posts/{job_post_id}", response_model=JobPostAvailabilityOut
)
async def get_job_post_availability(
    job_post_id: uuid.UUID,
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> JobPostAvailabilityOut:
    return await availability.get_for_job_post(job_post_id)


@availability_router.put(
    "/job-posts/{job_post_id}", response_model=JobPostAvailabilityOut
)
async def set_job_post_availability(
    job_post_id: uuid.UUID,
    payload: JobPostAvailabilityIn,
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> JobPostAvailabilityOut:
    return await availability.set_for_job_post(job_post_id, payload)


@interview_router.get(
    "/{application_id}/interview",
    response_model=InterviewRequestOut | None,
)
async def get_interview(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    interviews: InterviewService = Depends(get_interview_service),
) -> InterviewRequestOut | None:
    # Reuses get()'s owner-or-manage_applications check.
    await service.get(application_id, current_user)
    return await interviews.get_for_application(application_id)


@interview_router.put(
    "/{application_id}/interview",
    response_model=InterviewRequestOut,
    dependencies=[_manage_applications],
)
async def set_interview(
    application_id: uuid.UUID,
    payload: InterviewRequestIn,
    current_user: auth_entities.User = Depends(get_current_user),
    interviews: InterviewService = Depends(get_interview_service),
) -> InterviewRequestOut:
    return await interviews.set_request(
        application_id, payload, created_by_user_id=current_user.id
    )


@interview_router.delete(
    "/{application_id}/interview",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_manage_applications],
)
async def delete_interview(
    application_id: uuid.UUID,
    interviews: InterviewService = Depends(get_interview_service),
) -> None:
    await interviews.delete_request(application_id)


@interview_router.get(
    "/{application_id}/interview/open-slots",
    response_model=list[OpenSlotOut],
)
async def interview_open_slots(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> list[OpenSlotOut]:
    # Owner (the applicant) or a manage_applications user.
    await service.get(application_id, current_user)
    return await availability.open_slots_for_application(application_id)


@interview_router.post(
    "/{application_id}/interview/select",
    response_model=InterviewRequestOut,
)
async def select_interview_slot(
    application_id: uuid.UUID,
    payload: SelectSlotIn,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    interviews: InterviewService = Depends(get_interview_service),
) -> InterviewRequestOut:
    # Owner (the applicant) or a manage_applications user may confirm a slot.
    await service.get(application_id, current_user)
    return await interviews.select_slot(
        application_id, payload, selected_by_user_id=current_user.id
    )
