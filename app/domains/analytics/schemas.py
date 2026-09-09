import uuid
from datetime import date

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


class AnalyticsOverviewOut(BaseModel):
    period: str
    position_id: uuid.UUID | None = None
    hiring: HiringAnalyticsOut
    roles: RolesAnalyticsOut
    assessments: AssessmentsAnalyticsOut
    evaluations: EvaluationsAnalyticsOut
