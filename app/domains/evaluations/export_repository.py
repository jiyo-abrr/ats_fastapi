"""Applicant projections for evaluation exports, shared by HTTP and workers."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.applications.models import Application
from app.domains.applications.repository import ApplicationRepository


@dataclass(frozen=True)
class ExportApplicant:
    id: uuid.UUID
    applicant_id: uuid.UUID
    applicant_first_name: str
    applicant_last_name: str
    applicant_email: str
    status: str
    created_at: datetime | None
    resume_object_key: str | None


class EvaluationExportRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def applicants(
        self, job_post_id: uuid.UUID, *, statuses: list[str], limit: int
    ) -> list[ExportApplicant]:
        query = await ApplicationRepository(self.db).list_for_review(
            job_post_id=job_post_id, statuses=statuses
        )
        rows = (
            await self.db.execute(
                query.add_columns(Application.resume_object_key)
                .where(Application.hr_assessed.is_(False))
                .limit(limit)
            )
        ).all()
        return [
            ExportApplicant(
                id=r.id,
                applicant_id=r.applicant_id,
                applicant_first_name=r.applicant_first_name,
                applicant_last_name=r.applicant_last_name,
                applicant_email=r.applicant_email,
                status=r.status,
                created_at=r.created_at,
                resume_object_key=r.resume_object_key,
            )
            for r in rows
        ]
