import uuid
from datetime import date, datetime

from pydantic import BaseModel


class ActivityPointOut(BaseModel):
    date: date
    count: int


class StatusCountOut(BaseModel):
    key: str
    count: int


class HiringAnalyticsOut(BaseModel):
    total_applications: int
    unique_applicants: int
    active_candidates: int
    hires: int
    hire_conversion_rate: float
    overdue_assessments: int
    by_status: list[StatusCountOut]
    application_activity: list[ActivityPointOut]


class RolePerformanceOut(BaseModel):
    id: uuid.UUID
    job_title: str
    status: str
    position_title: str
    location_label: str
    application_count: int
    active_candidates: int
    hires: int
    hire_conversion_rate: float


class PositionPerformanceOut(BaseModel):
    id: uuid.UUID
    position_title: str
    job_post_count: int
    application_count: int
    active_candidates: int
    hires: int
    hire_conversion_rate: float


class RolesAnalyticsOut(BaseModel):
    total_job_posts: int
    published_job_posts: int
    draft_job_posts: int
    roles: list[RolePerformanceOut]
    positions: list[PositionPerformanceOut]


class AssessmentTemplateAnalyticsOut(BaseModel):
    template_type: str
    attempts: int
    not_started: int
    in_progress: int
    completed: int
    expired: int
    completion_rate: float
    average_completion_minutes: float | None


class AssessmentsAnalyticsOut(BaseModel):
    total_attempts: int
    started_attempts: int
    completed_attempts: int
    expired_attempts: int
    completion_rate: float
    started_completion_rate: float
    average_completion_minutes: float | None
    reopen_count: int
    templates: list[AssessmentTemplateAnalyticsOut]


class EvaluationDimensionOut(BaseModel):
    category: str
    dimension: str
    strong: int
    qualified: int
    below_bar: int
    na: int


class EvaluationsAnalyticsOut(BaseModel):
    evaluated_applications: int
    evaluation_coverage_rate: float
    average_fit_score: float | None
    recommendations: list[StatusCountOut]
    evaluation_activity: list[ActivityPointOut]
    fit_score_bands: list[StatusCountOut]
    score_dimensions: list[EvaluationDimensionOut]


class JobPostReportOut(BaseModel):
    """One row of the per-posting recruitment report — see
    AnalyticsRepository.job_post_reports()."""

    id: uuid.UUID
    job_title: str
    status: str
    published_at: datetime | None
    closed_at: datetime | None
    expires_at: datetime | None
    applied: int
    screened: int
    passed: int
    rejected: int
    accepted: int
    average_score: float | None
    highest_score: int | None
    recurring_applicants: int
    turnout: int
    engagement_rate: float
    posting_duration_days: int | None
    recommendation: str | None


class RecurringApplicantApplicationOut(BaseModel):
    job_post_id: uuid.UUID
    job_title: str
    status: str
    created_at: datetime


class RecurringApplicantOut(BaseModel):
    applicant_id: uuid.UUID
    name: str
    email: str
    application_count: int
    applications: list[RecurringApplicantApplicationOut]


class RankedJobPostOut(BaseModel):
    """One entry in a top-5 ranking (most turnout, most engaging, longest
    posting) — `value` means whatever the surrounding list is ranked by
    (turnout count, engagement %, or duration in days)."""

    id: uuid.UUID
    job_title: str
    value: float


class StrongestRecommendationOut(BaseModel):
    id: uuid.UUID
    job_title: str
    recommendation: str


class RecommendationCountOut(BaseModel):
    recommendation: str
    count: int


class RecruitmentInsightsOut(BaseModel):
    """The recruitment report's "Key Recruitment Insights" summary — see
    AnalyticsRepository.recruitment_insights()."""

    top_turnout: list[RankedJobPostOut]
    top_engagement: list[RankedJobPostOut]
    top_duration: list[RankedJobPostOut]
    strongest_recommendation: StrongestRecommendationOut | None
    recommendation_distribution: list[RecommendationCountOut]
    recurring_applicants_total: int
    total_applied: int
    total_screened: int
    total_passed: int
    candidates_passed_rate: float


class LocationCountOut(BaseModel):
    key: str
    count: int
    latitude: float | None = None
    longitude: float | None = None


class AnalyticsOverviewOut(BaseModel):
    period: str
    position_id: uuid.UUID | None = None
    hiring: HiringAnalyticsOut
    roles: RolesAnalyticsOut
    assessments: AssessmentsAnalyticsOut
    evaluations: EvaluationsAnalyticsOut
