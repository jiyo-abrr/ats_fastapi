import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository
from app.domains.job_posts import entities
from app.domains.job_posts.models import JobPost as JobPostModel
from app.domains.job_posts.models import (
    JobPostCultureFitTemplate,
    JobPostExclusion,
    JobPostPreAssessmentTemplate,
    JobPostTag,
    JobPostTechnicalAssessmentTemplate,
)
from app.domains.tags.entities import Tag
from app.domains.tags.models import Tag as TagModel

_EAGER_OPTIONS = (
    selectinload(JobPostModel.company_address),
    selectinload(JobPostModel.position),
)


class JobPostRepository(BaseRepository[JobPostModel, entities.JobPost, uuid.UUID]):
    model = JobPostModel

    async def _to_entity(self, obj: JobPostModel) -> entities.JobPost:
        tags_result = await self.db.execute(
            select(TagModel)
            .join(JobPostTag, JobPostTag.tag_id == TagModel.id)
            .where(JobPostTag.job_post_id == obj.id)
        )
        tags = tags_result.scalars().all()

        exclusions_result = await self.db.execute(
            select(JobPostExclusion).where(JobPostExclusion.job_post_id == obj.id)
        )
        excluded_ids = [
            row.excluded_job_post_id for row in exclusions_result.scalars().all()
        ]

        pre_assessment_template_id = await self._get_attached_template_id(
            JobPostPreAssessmentTemplate, obj.id
        )
        culture_fit_template_id = await self._get_attached_template_id(
            JobPostCultureFitTemplate, obj.id
        )
        technical_assessment_template_id = await self._get_attached_template_id(
            JobPostTechnicalAssessmentTemplate, obj.id
        )

        return entities.JobPost(
            id=obj.id,
            job_title=obj.job_title,
            description=obj.description,
            requirements=obj.requirements,
            qualifications=obj.qualifications,
            salary_min=obj.salary_min,
            salary_max=obj.salary_max,
            employment_type=obj.employment_type,
            status=obj.status,
            company_address_id=obj.company_address_id,
            company_address_label=obj.company_address.label,
            position_id=obj.position_id,
            position_title=obj.position.title,
            assessment_window_days=obj.assessment_window_days,
            tags=[Tag(id=t.id, name=t.name, description=t.description) for t in tags],
            excluded_job_post_ids=excluded_ids,
            pre_assessment_template_id=pre_assessment_template_id,
            culture_fit_template_id=culture_fit_template_id,
            technical_assessment_template_id=technical_assessment_template_id,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    async def _get_attached_template_id(
        self, join_model, job_post_id: uuid.UUID
    ) -> uuid.UUID | None:
        result = await self.db.execute(
            select(join_model.template_id).where(join_model.job_post_id == job_post_id)
        )
        return result.scalar_one_or_none()

    def _to_model(self, entity: entities.JobPost) -> JobPostModel:
        return JobPostModel(
            id=entity.id,
            job_title=entity.job_title,
            description=entity.description,
            requirements=entity.requirements,
            qualifications=entity.qualifications,
            salary_min=entity.salary_min,
            salary_max=entity.salary_max,
            employment_type=entity.employment_type,
            status=entity.status,
            company_address_id=entity.company_address_id,
            position_id=entity.position_id,
            assessment_window_days=entity.assessment_window_days,
        )

    # Overridden: _to_entity accesses obj.company_address.label / obj.position.title
    # — under AsyncSession those relationships must already be loaded, so every
    # fetch path here eager-loads them.
    async def get_by_id(self, id: uuid.UUID) -> entities.JobPost | None:
        result = await self.db.execute(
            select(JobPostModel).where(JobPostModel.id == id).options(*_EAGER_OPTIONS)
        )
        obj = result.scalar_one_or_none()
        return await self._to_entity(obj) if obj is not None else None

    async def list_all(self) -> list[entities.JobPost]:
        result = await self.db.execute(
            select(JobPostModel).options(*_EAGER_OPTIONS)
        )
        return [await self._to_entity(obj) for obj in result.scalars().all()]

    async def status_counts(self) -> dict[str, int]:
        """`{status: count}` for the ATS dashboard — one GROUP BY, no entity
        hydration (so the eager-load rule above doesn't apply)."""
        result = await self.db.execute(
            select(JobPostModel.status, func.count()).group_by(JobPostModel.status)
        )
        return {row[0]: row[1] for row in result.all()}

    async def update(self, entity: entities.JobPost) -> None:
        obj = await self.db.get(JobPostModel, entity.id)
        if obj is None:
            return
        obj.job_title = entity.job_title
        obj.description = entity.description
        obj.requirements = entity.requirements
        obj.qualifications = entity.qualifications
        obj.salary_min = entity.salary_min
        obj.salary_max = entity.salary_max
        obj.employment_type = entity.employment_type
        obj.status = entity.status
        obj.company_address_id = entity.company_address_id
        obj.position_id = entity.position_id
        obj.assessment_window_days = entity.assessment_window_days

    async def add_tag(self, job_post_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        if await self.db.get(JobPostTag, (job_post_id, tag_id)) is not None:
            return
        self.db.add(JobPostTag(job_post_id=job_post_id, tag_id=tag_id))

    async def remove_tag(self, job_post_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        row = await self.db.get(JobPostTag, (job_post_id, tag_id))
        if row is not None:
            await self.db.delete(row)

    async def add_exclusion(
        self, job_post_id: uuid.UUID, excluded_job_post_id: uuid.UUID
    ) -> None:
        existing = await self.db.get(
            JobPostExclusion, (job_post_id, excluded_job_post_id)
        )
        if existing is not None:
            return
        self.db.add(
            JobPostExclusion(
                job_post_id=job_post_id, excluded_job_post_id=excluded_job_post_id
            )
        )

    async def remove_exclusion(
        self, job_post_id: uuid.UUID, excluded_job_post_id: uuid.UUID
    ) -> None:
        row = await self.db.get(
            JobPostExclusion, (job_post_id, excluded_job_post_id)
        )
        if row is not None:
            await self.db.delete(row)

    # --- assessment template attachments (one pair of methods per type,
    # each its own real-FK join table with UniqueConstraint(job_post_id)
    # enforcing "at most one per job post") -----------------------------

    async def has_pre_assessment_template(self, job_post_id: uuid.UUID) -> bool:
        return (
            await self.db.get(JobPostPreAssessmentTemplate, job_post_id) is not None
        )

    async def set_pre_assessment_template(
        self, job_post_id: uuid.UUID, template_id: uuid.UUID
    ) -> None:
        self.db.add(
            JobPostPreAssessmentTemplate(
                job_post_id=job_post_id, template_id=template_id
            )
        )

    async def remove_pre_assessment_template(self, job_post_id: uuid.UUID) -> None:
        row = await self.db.get(JobPostPreAssessmentTemplate, job_post_id)
        if row is not None:
            await self.db.delete(row)

    async def has_culture_fit_template(self, job_post_id: uuid.UUID) -> bool:
        return await self.db.get(JobPostCultureFitTemplate, job_post_id) is not None

    async def set_culture_fit_template(
        self, job_post_id: uuid.UUID, template_id: uuid.UUID
    ) -> None:
        self.db.add(
            JobPostCultureFitTemplate(job_post_id=job_post_id, template_id=template_id)
        )

    async def remove_culture_fit_template(self, job_post_id: uuid.UUID) -> None:
        row = await self.db.get(JobPostCultureFitTemplate, job_post_id)
        if row is not None:
            await self.db.delete(row)

    async def has_technical_assessment_template(self, job_post_id: uuid.UUID) -> bool:
        return (
            await self.db.get(JobPostTechnicalAssessmentTemplate, job_post_id)
            is not None
        )

    async def set_technical_assessment_template(
        self, job_post_id: uuid.UUID, template_id: uuid.UUID
    ) -> None:
        self.db.add(
            JobPostTechnicalAssessmentTemplate(
                job_post_id=job_post_id, template_id=template_id
            )
        )

    async def remove_technical_assessment_template(
        self, job_post_id: uuid.UUID
    ) -> None:
        row = await self.db.get(JobPostTechnicalAssessmentTemplate, job_post_id)
        if row is not None:
            await self.db.delete(row)
