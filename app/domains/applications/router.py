import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.applications.dependencies import (
    get_application_service,
    get_evaluation_service,
    get_interview_availability_service,
    get_interview_service,
)
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.evaluations import (
    ApplicationEvaluationOut,
    EvaluationImportIn,
    EvaluationImportResultOut,
    EvaluationService,
    JobEvaluationRowOut,
)
from app.domains.applications.exceptions import ResumeUnavailableError
from app.domains.applications.export import build_evaluation_pack
from app.domains.applications.interview_availability import (
    DateOverrideOut,
    DateOverridesIn,
    GlobalAvailabilityIn,
    GlobalAvailabilityOut,
    InterviewAvailabilityService,
    InterviewerOut,
    JobPostAvailabilityIn,
    JobPostAvailabilityOut,
    OpenSlotOut,
)
from app.domains.applications.interviews import (
    InterviewRequestIn,
    InterviewRequestOut,
    InterviewService,
    InterviewStatusOut,
    SelectSlotIn,
    UpcomingInterviewOut,
)
from app.domains.applications.schemas import (
    ApplicantSummaryOut,
    ApplicationAssessmentsOut,
    ApplicationCreate,
    ApplicationOut,
    ApplicationReviewOut,
    ApplicationScorecardOut,
    ApplicationStatsOut,
    ApplicationStatusUpdate,
    ApplicationSummaryOut,
    AssessmentDeadlineExtensionOut,
    AttemptSummaryOut,
    EvaluationSummaryOut,
    ExtendAssessmentDeadlineRequest,
    JobAssessmentReviewRowOut,
)
from app.domains.applications.service import ApplicationService
from app.domains.assessments.attempts.dependencies import get_assessment_service
from app.domains.assessments.attempts.schemas import (
    AssessmentAttemptOut,
    AttemptReviewOut,
)
from app.domains.assessments.attempts.service import AssessmentService
from app.domains.auth import entities as auth_entities
from app.domains.auth.dependencies import get_current_user
from app.domains.job_posts.dependencies import get_job_post_service
from app.domains.job_posts.service import JobPostService
from app.domains.rbac.dependencies import require_permission

_manage_applications = Depends(require_permission("manage_applications"))

router = APIRouter(prefix="/applications", tags=["applications"])

# Interview availability — the recurring weekly windows candidates self-book
# into (global on the /calendar page, or per job post).
scheduling_router = APIRouter(
    prefix="/interview-availability",
    tags=["interview-availability"],
    dependencies=[_manage_applications],
)


@scheduling_router.get("", response_model=GlobalAvailabilityOut)
async def get_global_availability(
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> GlobalAvailabilityOut:
    return await availability.get_global()


@scheduling_router.put("", response_model=GlobalAvailabilityOut)
async def set_global_availability(
    payload: GlobalAvailabilityIn,
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> GlobalAvailabilityOut:
    return await availability.set_global(payload)


@scheduling_router.get(
    "/overrides", response_model=list[DateOverrideOut]
)
async def get_date_overrides(
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> list[DateOverrideOut]:
    return await availability.get_overrides()


@scheduling_router.put(
    "/overrides", response_model=list[DateOverrideOut]
)
async def set_date_overrides(
    payload: DateOverridesIn,
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> list[DateOverrideOut]:
    """Whole-list replace of the global date overrides — what the dedicated
    overrides page and its CSV import send."""
    return await availability.set_overrides(payload)


@scheduling_router.get("/upcoming", response_model=list[UpcomingInterviewOut])
async def upcoming_interviews(
    interviews: InterviewService = Depends(get_interview_service),
) -> list[UpcomingInterviewOut]:
    return await interviews.upcoming()


@scheduling_router.get("/schedule", response_model=list[UpcomingInterviewOut])
async def interview_schedule(
    start: datetime,
    end: datetime,
    interviews: InterviewService = Depends(get_interview_service),
) -> list[UpcomingInterviewOut]:
    """Confirmed interviews within `[start, end)` — the calendar's visible
    window."""
    return await interviews.schedule(start=start, end=end)


@scheduling_router.get(
    "/statuses", response_model=list[InterviewStatusOut]
)
async def job_post_interview_statuses(
    job_post_id: uuid.UUID,
    interviews: InterviewService = Depends(get_interview_service),
) -> list[InterviewStatusOut]:
    return await interviews.statuses_for_job_post(job_post_id)


@scheduling_router.get("/staff", response_model=list[InterviewerOut])
async def list_interview_staff(
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> list[InterviewerOut]:
    return await availability.list_staff()


@scheduling_router.get(
    "/job-posts/{job_post_id}", response_model=JobPostAvailabilityOut
)
async def get_job_post_availability(
    job_post_id: uuid.UUID,
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
) -> JobPostAvailabilityOut:
    return await availability.get_for_job_post(job_post_id)


@scheduling_router.put(
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


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreate,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
) -> ApplicationOut:
    application = await service.create(
        job_post_id=payload.job_post_id, current_user=current_user
    )
    # Router-level composition, not a service-to-service dependency: creating
    # an application's assessment attempts touches both applications and
    # assessments, and those two domains can't depend on each other (assessments
    # already depends on applications — see applications-status-pipeline.md's
    # scheduler section for the same cycle problem, resolved the same way).
    await assessment_service.create_attempts_for_application(
        application.id, payload.job_post_id
    )
    return application


@router.get("/me", response_model=Page[ApplicationSummaryOut])
async def list_my_applications(
    job_post_id: uuid.UUID | None = None,
    current_user: auth_entities.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    interviews: InterviewService = Depends(get_interview_service),
) -> Page[ApplicationSummaryOut]:
    query = await service.list_for_applicant(current_user.id, job_post_id=job_post_id)

    async def _transform(rows):
        interview_ids = [r.id for r in rows if r.status == ApplicationStatus.INTERVIEW]
        pending = await interviews.pending_selection_application_ids(interview_ids)
        out = []
        for r in rows:
            dto = ApplicationSummaryOut.model_validate(r)
            dto.needs_interview_pick = r.id in pending
            out.append(dto)
        return out

    return await apaginate(db, query, transformer=_transform)


@router.get(
    "/stats",
    response_model=ApplicationStatsOut,
    dependencies=[_manage_applications],
)
async def application_stats(
    job_post_id: uuid.UUID | None = None,
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationStatsOut:
    return ApplicationStatsOut(**await service.stats(job_post_id))


@router.get(
    "",
    response_model=Page[ApplicationReviewOut],
    dependencies=[_manage_applications],
)
async def list_applications(
    job_post_id: uuid.UUID | None = None,
    status: list[ApplicationStatus] | None = Query(None),
    applicant_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
) -> Page[ApplicationReviewOut]:
    query = await service.list_for_review(
        job_post_id=job_post_id,
        statuses=[s.value for s in status] if status else None,
        applicant_id=applicant_id,
    )
    return await apaginate(
        db,
        query,
        transformer=lambda rows: [ApplicationReviewOut.model_validate(r) for r in rows],
    )


@router.get(
    "/applicants",
    response_model=Page[ApplicantSummaryOut],
    dependencies=[_manage_applications],
)
async def list_applicants(
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
) -> Page[ApplicantSummaryOut]:
    query = await service.list_applicants(search=search)
    return await apaginate(
        db,
        query,
        transformer=lambda rows: [ApplicantSummaryOut.model_validate(r) for r in rows],
    )


@router.get(
    "/assessment-scorecard",
    response_model=Page[ApplicationScorecardOut],
    dependencies=[_manage_applications],
)
async def assessment_scorecard(
    job_post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
    evaluations: EvaluationService = Depends(get_evaluation_service),
) -> Page[ApplicationScorecardOut]:
    query = await service.list_for_review(job_post_id=job_post_id, statuses=None)

    async def _transform(rows):
        ids = [r.id for r in rows]
        summaries = await assessment_service.summaries_for_applications(ids)
        evals = await evaluations.latest_summaries_for_applications(ids)
        return [
            ApplicationScorecardOut(
                id=r.id,
                created_at=r.created_at,
                status=r.status,
                applicant_first_name=r.applicant_first_name,
                applicant_last_name=r.applicant_last_name,
                applicant_email=r.applicant_email,
                assessments=[
                    AttemptSummaryOut(**summary) for summary in summaries.get(r.id, [])
                ],
                evaluation=(
                    EvaluationSummaryOut(**evals[r.id]) if r.id in evals else None
                ),
            )
            for r in rows
        ]

    return await apaginate(db, query, transformer=_transform)


@router.get(
    "/assessment-review",
    response_model=Page[JobAssessmentReviewRowOut],
    dependencies=[_manage_applications],
)
async def job_assessment_review(
    job_post_id: uuid.UUID,
    template_type: str,
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
) -> Page[JobAssessmentReviewRowOut]:
    query = await service.list_for_review(job_post_id=job_post_id, statuses=None)

    async def _transform(rows):
        out: list[JobAssessmentReviewRowOut] = []
        for r in rows:
            reviews = await assessment_service.list_review_for_application(r.id)
            match = next(
                (rv for rv in reviews if rv["template_type"] == template_type),
                None,
            )
            out.append(
                JobAssessmentReviewRowOut(
                    application_id=r.id,
                    applicant_first_name=r.applicant_first_name,
                    applicant_last_name=r.applicant_last_name,
                    applicant_email=r.applicant_email,
                    attempt=AttemptReviewOut.model_validate(match) if match else None,
                )
            )
        return out

    return await apaginate(db, query, transformer=_transform)


@router.get("/export", dependencies=[_manage_applications])
async def export_evaluation_pack(
    job_post_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
    job_post_service: JobPostService = Depends(get_job_post_service),
) -> Response:
    """ZIP for external AI evaluation: job spec + rubric + every applicant's
    résumé and assessment answers."""
    job = await job_post_service.get(job_post_id)
    query = await service.list_for_review(job_post_id=job_post_id, statuses=None)
    rows = (await db.execute(query)).all()

    applicants: list[dict] = []
    for row in rows:
        try:
            data, _content_type, filename = await service.get_resume(
                row.id, current_user
            )
            resume = (data, filename)
        except ResumeUnavailableError:
            resume = None
        reviews = await assessment_service.list_review_for_application(row.id)
        applicants.append({"row": row, "resume": resume, "reviews": reviews})

    payload = build_evaluation_pack(job=job, applicants=applicants)
    slug = re.sub(r"[^a-z0-9]+", "-", job.job_title.lower()).strip("-") or "job"
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{slug}-evaluation-pack.zip"'
            )
        },
    )


@router.get(
    "/evaluations",
    response_model=Page[JobEvaluationRowOut],
    dependencies=[_manage_applications],
)
async def job_evaluations(
    job_post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    evaluations: EvaluationService = Depends(get_evaluation_service),
) -> Page[JobEvaluationRowOut]:
    """One row per applicant with their full latest AI evaluation (recommendation,
    fit score, per-dimension scores) — for the Compare tab's side-by-side view."""
    query = await service.list_for_review(job_post_id=job_post_id, statuses=None)

    async def _transform(rows):
        full = await evaluations.latest_full_for_applications([r.id for r in rows])
        return [
            JobEvaluationRowOut(
                application_id=r.id,
                applicant_first_name=r.applicant_first_name,
                applicant_last_name=r.applicant_last_name,
                applicant_email=r.applicant_email,
                evaluation=full.get(r.id),
            )
            for r in rows
        ]

    return await apaginate(db, query, transformer=_transform)


@router.get("/evaluations/export", dependencies=[_manage_applications])
async def export_evaluations_csv(
    job_post_id: uuid.UUID,
    evaluations: EvaluationService = Depends(get_evaluation_service),
) -> Response:
    """Flat CSV: latest AI evaluation per applicant, one column per dimension."""
    csv_text = await evaluations.evaluation_csv(job_post_id)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="evaluations.csv"'},
    )


@router.post(
    "/evaluations/import",
    response_model=EvaluationImportResultOut,
    dependencies=[_manage_applications],
)
async def import_evaluations(
    payload: EvaluationImportIn,
    current_user: auth_entities.User = Depends(get_current_user),
    evaluations: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationImportResultOut:
    return await evaluations.import_results(
        payload, imported_by_user_id=current_user.id
    )


@router.get(
    "/{application_id}/evaluation",
    response_model=ApplicationEvaluationOut,
    dependencies=[_manage_applications],
)
async def get_application_evaluation(
    application_id: uuid.UUID,
    evaluations: EvaluationService = Depends(get_evaluation_service),
) -> ApplicationEvaluationOut:
    return await evaluations.get_for_application(application_id)


@router.get(
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


@router.put(
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


@router.delete(
    "/{application_id}/interview",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_manage_applications],
)
async def delete_interview(
    application_id: uuid.UUID,
    interviews: InterviewService = Depends(get_interview_service),
) -> None:
    await interviews.delete_request(application_id)


@router.get(
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


@router.post(
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


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.get(application_id, current_user)


@router.get("/{application_id}/resume")
async def download_resume(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> Response:
    data, content_type, filename = await service.get_resume(
        application_id, current_user
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{application_id}/withdraw", response_model=ApplicationOut)
async def withdraw_application(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.withdraw(application_id, current_user)


@router.patch(
    "/{application_id}/status",
    response_model=ApplicationOut,
    dependencies=[_manage_applications],
)
async def update_application_status(
    application_id: uuid.UUID,
    payload: ApplicationStatusUpdate,
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.update_status(application_id, payload.status)


@router.patch(
    "/{application_id}/extend-assessment-deadline",
    response_model=ApplicationOut,
    dependencies=[_manage_applications],
)
async def extend_assessment_deadline(
    application_id: uuid.UUID,
    payload: ExtendAssessmentDeadlineRequest,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.extend_assessment_deadline(
        application_id,
        new_deadline=payload.new_deadline,
        extend_by_days=payload.extend_by_days,
        reason=payload.reason,
        current_user=current_user,
    )


@router.get(
    "/{application_id}/assessments/review",
    response_model=list[AttemptReviewOut],
    dependencies=[_manage_applications],
)
async def get_application_assessments_review(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
) -> list[AttemptReviewOut]:
    # Reuses ApplicationService.get() for the existence + access check
    # (the route's _manage_applications dep already gates the permission).
    await service.get(application_id, current_user)
    reviews = await assessment_service.list_review_for_application(application_id)
    return [AttemptReviewOut.model_validate(r) for r in reviews]


@router.get(
    "/{application_id}/assessments",
    response_model=ApplicationAssessmentsOut,
)
async def get_application_assessments(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
) -> ApplicationAssessmentsOut:
    # ApplicationService.get() enforces the owner-or-manage_applications
    # check — the same rule this endpoint needs, so it's reused rather than
    # duplicated here.
    await service.get(application_id, current_user)
    attempts = await assessment_service.list_for_application(application_id)
    extensions = await service.list_deadline_extensions(application_id)
    return ApplicationAssessmentsOut(
        attempts=[AssessmentAttemptOut.model_validate(a) for a in attempts],
        deadline_extensions=[
            AssessmentDeadlineExtensionOut.model_validate(e) for e in extensions
        ],
    )
