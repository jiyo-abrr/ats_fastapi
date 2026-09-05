import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository
from app.domains.job_posts import entities
from app.domains.job_posts.models import JobPost as JobPostModel
from app.domains.job_posts.models import JobPostExclusion, JobPostTag
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
            tags=[Tag(id=t.id, name=t.name, description=t.description) for t in tags],
            excluded_job_post_ids=excluded_ids,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

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
