import uuid
from datetime import datetime

from sqlalchemy import Select, func, or_, select

from app.core.repository import BaseRepository
from app.domains.applications import entities
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.models import Application as ApplicationModel
from app.domains.applications.models import AssessmentDeadlineExtension
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
            assessment_deadline=obj.assessment_deadline,
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
            assessment_deadline=entity.assessment_deadline,
        )

    async def update_status(self, application_id: uuid.UUID, status: str) -> None:
        obj = await self.db.get(ApplicationModel, application_id)
        if obj is None:
            return
        obj.status = status

    async def set_assessment_deadline(
        self, application_id: uuid.UUID, new_deadline
    ) -> None:
        obj = await self.db.get(ApplicationModel, application_id)
        if obj is None:
            return
        obj.assessment_deadline = new_deadline

    async def add_deadline_extension(
        self, extension: entities.AssessmentDeadlineExtension
    ) -> None:
        self.db.add(
            AssessmentDeadlineExtension(
                id=extension.id,
                application_id=extension.application_id,
                extended_by_user_id=extension.extended_by_user_id,
                reason=extension.reason,
                previous_deadline=extension.previous_deadline,
                new_deadline=extension.new_deadline,
            )
        )

    async def list_deadline_extensions(
        self, application_id: uuid.UUID
    ) -> list[entities.AssessmentDeadlineExtension]:
        result = await self.db.execute(
            select(AssessmentDeadlineExtension)
            .where(AssessmentDeadlineExtension.application_id == application_id)
            .order_by(AssessmentDeadlineExtension.extended_at.desc())
        )
        return [
            entities.AssessmentDeadlineExtension(
                id=row.id,
                application_id=row.application_id,
                extended_by_user_id=row.extended_by_user_id,
                reason=row.reason,
                previous_deadline=row.previous_deadline,
                new_deadline=row.new_deadline,
                extended_at=row.extended_at,
            )
            for row in result.scalars().all()
        ]

    async def list_overdue_applied(self, now: datetime) -> list[entities.Application]:
        """Applications still `applied` whose assessment_deadline has passed
        — candidates for the disqualification sweep."""
        result = await self.db.execute(
            select(ApplicationModel).where(
                ApplicationModel.status == ApplicationStatus.APPLIED.value,
                ApplicationModel.assessment_deadline.is_not(None),
                ApplicationModel.assessment_deadline < now,
            )
        )
        return [await self._to_entity(obj) for obj in result.scalars().all()]

    async def status_counts(
        self, job_post_id: uuid.UUID | None = None
    ) -> dict[str, int]:
        """`{status: count}` for the review dashboard — one GROUP BY, optionally
        scoped to a single job post."""
        query = select(ApplicationModel.status, func.count()).group_by(
            ApplicationModel.status
        )
        if job_post_id is not None:
            query = query.where(ApplicationModel.job_post_id == job_post_id)
        result = await self.db.execute(query)
        return {row[0]: row[1] for row in result.all()}

    async def job_post_has_applications(self, job_post_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(ApplicationModel.id)
            .where(ApplicationModel.job_post_id == job_post_id)
            .limit(1)
        )
        return result.first() is not None

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
        self,
        *,
        job_post_id: uuid.UUID | None,
        statuses: list[str] | None,
        applicant_id: uuid.UUID | None = None,
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
        if statuses:
            query = query.where(ApplicationModel.status.in_(statuses))
        if applicant_id is not None:
            query = query.where(ApplicationModel.applicant_id == applicant_id)
        return query

    # Projection query for an applicant's own list — joined only to job_posts
    # for the job title, so "my applications" doesn't need a second
    # round-trip to /job-posts/{id} per row. `job_post_id` scopes it to one
    # job post (the Apply button's "do I already have an application here").
    async def list_for_applicant(
        self, applicant_id: uuid.UUID, job_post_id: uuid.UUID | None = None
    ) -> Select:
        query = (
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
        if job_post_id is not None:
            query = query.where(ApplicationModel.job_post_id == job_post_id)
        return query

    # Applicant-centric roll-up for the HR/admin "Applicants" list: one row
    # per person who has at least one application, with a count and their
    # most recent apply date. Distinct from list_for_review (one row per
    # application) — this is grouped.
    async def list_applicants(self, *, search: str | None) -> Select:
        query = (
            select(
                ApplicationModel.applicant_id,
                UserModel.first_name.label("first_name"),
                UserModel.last_name.label("last_name"),
                UserModel.email.label("email"),
                func.count(ApplicationModel.id).label("application_count"),
                func.max(ApplicationModel.created_at).label("latest_applied_at"),
            )
            .join(UserModel, UserModel.id == ApplicationModel.applicant_id)
            .group_by(
                ApplicationModel.applicant_id,
                UserModel.first_name,
                UserModel.last_name,
                UserModel.email,
            )
            .order_by(func.max(ApplicationModel.created_at).desc())
        )
        if search:
            like = f"%{search}%"
            query = query.where(
                or_(
                    UserModel.first_name.ilike(like),
                    UserModel.last_name.ilike(like),
                    UserModel.email.ilike(like),
                )
            )
        return query
