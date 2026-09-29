"""One export workflow with caller-supplied limits and authorized resume access."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.domains.applications.enums import EVALUATION_ELIGIBLE_STATUSES
from app.domains.assessments.attempts.service import AssessmentService
from app.domains.evaluations.export_repository import (
    EvaluationExportRepository,
    ExportApplicant,
)
from app.domains.evaluations.pack import build_evaluation_pack
from app.domains.job_posts.exceptions import JobPostNotFoundError
from app.domains.job_posts.repository import JobPostRepository


class ExportLimitExceeded(Exception):
    """The selected export exceeds its caller's count or byte budget."""


@dataclass(frozen=True)
class ExportPolicy:
    max_applicants: int
    max_resume_bytes: int | None = None


@dataclass(frozen=True)
class PreparedExport:
    job_title: str
    payload: bytes


ResumeLoader = Callable[[ExportApplicant], Awaitable[tuple[bytes, str] | None]]


class PrepareEvaluationExport:
    def __init__(
        self,
        exports: EvaluationExportRepository,
        job_posts: JobPostRepository,
        assessments: AssessmentService,
    ):
        self.exports = exports
        self.job_posts = job_posts
        self.assessments = assessments

    async def execute(
        self,
        job_post_id: uuid.UUID,
        *,
        statuses: list[str] | None,
        policy: ExportPolicy,
        load_resume: ResumeLoader,
    ) -> PreparedExport:
        job = await self.job_posts.get_by_id(job_post_id)
        if job is None:
            raise JobPostNotFoundError(f"Job post '{job_post_id}' not found")
        rows = await self.exports.applicants(
            job_post_id,
            statuses=statuses or EVALUATION_ELIGIBLE_STATUSES,
            limit=policy.max_applicants + 1,
        )
        if len(rows) > policy.max_applicants:
            raise ExportLimitExceeded(
                f"More than {policy.max_applicants} applicants match."
            )
        applicants = []
        total_bytes = 0
        for row in rows:
            resume = await load_resume(row)
            if resume:
                total_bytes += len(resume[0])
                if (
                    policy.max_resume_bytes is not None
                    and total_bytes > policy.max_resume_bytes
                ):
                    raise ExportLimitExceeded(
                        "The résumés exceed the "
                        f"{policy.max_resume_bytes // (1024 * 1024)} MiB export limit."
                    )
            reviews = await self.assessments.list_review_for_application(row.id)
            applicants.append({"row": row, "resume": resume, "reviews": reviews})
        return PreparedExport(
            job_title=job.job_title,
            payload=build_evaluation_pack(job=job, applicants=applicants),
        )
