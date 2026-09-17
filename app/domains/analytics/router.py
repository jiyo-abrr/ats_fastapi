import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.domains.analytics.dependencies import get_analytics_service
from app.domains.analytics.schemas import (
    AnalyticsOverviewOut,
    JobPostReportOut,
    LocationCountOut,
    RecruitmentInsightsOut,
    RecurringApplicantOut,
)
from app.domains.analytics.service import AnalyticsService
from app.domains.rbac.dependencies import require_admin

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_admin)],
)


@router.get("/overview", response_model=AnalyticsOverviewOut)
async def analytics_overview(
    period: Literal["daily", "weekly", "monthly", "yearly"] = Query("daily"),
    position_id: uuid.UUID | None = None,
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsOverviewOut:
    return AnalyticsOverviewOut(
        **await service.overview(period=period, position_id=position_id)
    )


@router.get("/locations", response_model=list[LocationCountOut])
async def analytics_locations(
    position_id: uuid.UUID | None = None,
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[LocationCountOut]:
    """Ranked applicant-location counts + coordinates (geocoded via
    Nominatim, cached) for the locations bar chart and heatmap. Separate from
    /overview so a cold geocoding cache doesn't stall the rest of the
    dashboard."""
    return [
        LocationCountOut(**row)
        for row in await service.locations(position_id=position_id)
    ]


@router.get("/job-posts", response_model=list[JobPostReportOut])
async def analytics_job_posts(
    position_id: uuid.UUID | None = None,
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[JobPostReportOut]:
    """Per-posting recruitment report: lifetime funnel counts, assessment
    scores, recurring applicants, turnout/engagement, posting duration, and
    a deterministic (non-ML) recommended action for each job post."""
    return [
        JobPostReportOut(**row)
        for row in await service.job_post_reports(position_id=position_id)
    ]


@router.get("/recruitment-insights", response_model=RecruitmentInsightsOut)
async def analytics_recruitment_insights(
    position_id: uuid.UUID | None = None,
    service: AnalyticsService = Depends(get_analytics_service),
) -> RecruitmentInsightsOut:
    """Key Recruitment Insights summary for the Reports tab: top-5 rankings
    (turnout, engagement, posting duration), the strongest recommendation,
    the recommendation distribution, and pipeline totals — all computed
    server-side so the frontend only renders, never re-derives, this."""
    return RecruitmentInsightsOut(
        **await service.recruitment_insights(position_id=position_id)
    )


@router.get("/recurring-applicants", response_model=list[RecurringApplicantOut])
async def analytics_recurring_applicants(
    position_id: uuid.UUID | None = None,
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[RecurringApplicantOut]:
    """Applicants with more than one application anywhere in the system,
    with their full application history — the detail page behind the
    recruitment report's "recurring applicants" insight card."""
    return [
        RecurringApplicantOut(**row)
        for row in await service.recurring_applicants(position_id=position_id)
    ]
