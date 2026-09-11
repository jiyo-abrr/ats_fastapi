import uuid
from collections import defaultdict
from collections.abc import Sequence

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

    @staticmethod
    def _build(
        obj: JobPostModel,
        *,
        tags: list[TagModel],
        excluded_ids: list[uuid.UUID],
        pre_id: uuid.UUID | None,
        cf_id: uuid.UUID | None,
        tech_id: uuid.UUID | None,
    ) -> entities.JobPost:
        return entities.JobPost(
            id=obj.id,
            job_title=obj.job_title,
            description=obj.description,
            requirements=obj.requirements,
            qualifications=obj.qualifications,
            salary_min=obj.salary_min,
            salary_max=obj.salary_max,
            currency=obj.currency,
            employment_type=obj.employment_type,
            status=obj.status,
            company_address_id=obj.company_address_id,
            company_address_label=obj.company_address.label,
            position_id=obj.position_id,
            position_title=obj.position.title,
            assessment_window_days=obj.assessment_window_days,
            tags=[Tag(id=t.id, name=t.name, description=t.description) for t in tags],
            excluded_job_post_ids=excluded_ids,
            pre_assessment_template_id=pre_id,
            culture_fit_template_id=cf_id,
            technical_assessment_template_id=tech_id,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    async def _to_entity(self, obj: JobPostModel) -> entities.JobPost:
        # Single-row path (get_by_id) — a handful of small lookups is fine here;
        # the paginated list path uses map_many() which bulk-fetches instead
        # (see review F08).
        tags = list(
            (
                await self.db.execute(
                    select(TagModel)
                    .join(JobPostTag, JobPostTag.tag_id == TagModel.id)
                    .where(JobPostTag.job_post_id == obj.id)
                )
            )
            .scalars()
            .all()
        )
        excluded_ids = [
            row[0]
            for row in (
                await self.db.execute(
                    select(JobPostExclusion.excluded_job_post_id).where(
                        JobPostExclusion.job_post_id == obj.id
                    )
                )
            ).all()
        ]
        return self._build(
            obj,
            tags=tags,
            excluded_ids=excluded_ids,
            pre_id=await self._get_attached_template_id(
                JobPostPreAssessmentTemplate, obj.id
            ),
            cf_id=await self._get_attached_template_id(
                JobPostCultureFitTemplate, obj.id
            ),
            tech_id=await self._get_attached_template_id(
                JobPostTechnicalAssessmentTemplate, obj.id
            ),
        )

    async def map_many(self, rows: Sequence[JobPostModel]) -> list[entities.JobPost]:
        """Bulk-fetch related data for a whole page in a fixed number of
        queries (review F08): 1 for tags, 1 for exclusions, 3 for the template
        attachments — regardless of page size."""
        rows = list(rows)
        if not rows:
            return []
        ids = [r.id for r in rows]

        tags_by_post: dict[uuid.UUID, list[TagModel]] = defaultdict(list)
        for jp_id, tag in (
            await self.db.execute(
                select(JobPostTag.job_post_id, TagModel)
                .join(TagModel, TagModel.id == JobPostTag.tag_id)
                .where(JobPostTag.job_post_id.in_(ids))
            )
        ).all():
            tags_by_post[jp_id].append(tag)

        excl_by_post: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        for jp_id, excl_id in (
            await self.db.execute(
                select(
                    JobPostExclusion.job_post_id,
                    JobPostExclusion.excluded_job_post_id,
                ).where(JobPostExclusion.job_post_id.in_(ids))
            )
        ).all():
            excl_by_post[jp_id].append(excl_id)

        async def _template_map(join_model) -> dict[uuid.UUID, uuid.UUID]:
            return {
                jp_id: t_id
                for jp_id, t_id in (
                    await self.db.execute(
                        select(join_model.job_post_id, join_model.template_id).where(
                            join_model.job_post_id.in_(ids)
                        )
                    )
                ).all()
            }

        pre = await _template_map(JobPostPreAssessmentTemplate)
        cf = await _template_map(JobPostCultureFitTemplate)
        tech = await _template_map(JobPostTechnicalAssessmentTemplate)

        return [
            self._build(
                r,
                tags=tags_by_post.get(r.id, []),
                excluded_ids=excl_by_post.get(r.id, []),
                pre_id=pre.get(r.id),
                cf_id=cf.get(r.id),
                tech_id=tech.get(r.id),
            )
            for r in rows
        ]

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
            currency=entity.currency,
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
        result = await self.db.execute(select(JobPostModel).options(*_EAGER_OPTIONS))
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
        obj.currency = entity.currency
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
        row = await self.db.get(JobPostExclusion, (job_post_id, excluded_job_post_id))
        if row is not None:
            await self.db.delete(row)

    # --- assessment template attachments (one pair of methods per type,
    # each its own real-FK join table with UniqueConstraint(job_post_id)
    # enforcing "at most one per job post") -----------------------------

    async def has_pre_assessment_template(self, job_post_id: uuid.UUID) -> bool:
        return await self.db.get(JobPostPreAssessmentTemplate, job_post_id) is not None

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
