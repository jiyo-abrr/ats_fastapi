import uuid

from sqlalchemy import Select, select

from app.core.repository import BaseRepository
from app.domains.applications import entities
from app.domains.applications.models import Application as ApplicationModel
from app.domains.auth.models import User as UserModel
from app.domains.job_posts.models import JobPost as JobPostModel


class ApplicationRepository(
    BaseRepository[ApplicationModel, entities.Application, uuid.UUID]
):
    model = ApplicationModel

    async def _to_entity(self, obj: ApplicationModel) -> entities.Application:
        return entities.Application(
            id=obj.id,
            job_post_id=obj.job_post_id,
            applicant_id=obj.applicant_id,
            status=obj.status,
            resume_object_key=obj.resume_object_key,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    def _to_model(self, entity: entities.Application) -> ApplicationModel:
        return ApplicationModel(
            id=entity.id,
            job_post_id=entity.job_post_id,
            applicant_id=entity.applicant_id,
            status=entity.status,
            resume_object_key=entity.resume_object_key,
        )

    async def update_status(self, application_id: uuid.UUID, status: str) -> None:
        obj = await self.db.get(ApplicationModel, application_id)
        if obj is None:
            return
        obj.status = status

    async def has_any_application_for(
        self, applicant_id: uuid.UUID, job_post_id: uuid.UUID
    ) -> bool:
        result = await self.db.execute(
            select(ApplicationModel.id).where(
                ApplicationModel.applicant_id == applicant_id,
                ApplicationModel.job_post_id == job_post_id,
            )
        )
        return result.first() is not None

    # Projection query for the HR/admin review list — joins job_posts + users
    # for a curated column set (job title, applicant name/email) rather than
    # hydrating full Application/JobPost/User entities. Bypasses QueryBuilder
    # (it only builds a select() against a single ORM class) — filtering is
    # explicit typed params instead of the generic JSON filter syntax.
    async def list_for_review(
        self, *, job_post_id: uuid.UUID | None, status: str | None
    ) -> Select:
        query = (
            select(
                ApplicationModel.id,
                ApplicationModel.status,
                ApplicationModel.created_at,
                ApplicationModel.job_post_id,
                JobPostModel.job_title,
                ApplicationModel.applicant_id,
                UserModel.first_name.label("applicant_first_name"),
                UserModel.last_name.label("applicant_last_name"),
                UserModel.email.label("applicant_email"),
            )
            .join(JobPostModel, JobPostModel.id == ApplicationModel.job_post_id)
            .join(UserModel, UserModel.id == ApplicationModel.applicant_id)
            .order_by(ApplicationModel.created_at.desc())
        )
        if job_post_id is not None:
            query = query.where(ApplicationModel.job_post_id == job_post_id)
        if status is not None:
            query = query.where(ApplicationModel.status == status)
        return query

    # Projection query for an applicant's own list — joined only to job_posts
    # for the job title, so "my applications" doesn't need a second
    # round-trip to /job-posts/{id} per row.
    async def list_for_applicant(self, applicant_id: uuid.UUID) -> Select:
        return (
            select(
                ApplicationModel.id,
                ApplicationModel.status,
                ApplicationModel.created_at,
                ApplicationModel.job_post_id,
                JobPostModel.job_title,
            )
            .join(JobPostModel, JobPostModel.id == ApplicationModel.job_post_id)
            .where(ApplicationModel.applicant_id == applicant_id)
            .order_by(ApplicationModel.created_at.desc())
        )
