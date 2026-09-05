import uuid

from app.core.repository import BaseRepository
from app.domains.job_posts import entities
from app.domains.job_posts.models import JobPost as JobPostModel
from app.domains.job_posts.models import JobPostExclusion, JobPostTag
from app.domains.tags.entities import Tag
from app.domains.tags.models import Tag as TagModel


class JobPostRepository(BaseRepository[JobPostModel, entities.JobPost, uuid.UUID]):
    model = JobPostModel

    def _to_entity(self, obj: JobPostModel) -> entities.JobPost:
        tags = (
            self.db.query(TagModel)
            .join(JobPostTag, JobPostTag.tag_id == TagModel.id)
            .filter(JobPostTag.job_post_id == obj.id)
            .all()
        )
        excluded_ids = [
            row.excluded_job_post_id
            for row in self.db.query(JobPostExclusion)
            .filter(JobPostExclusion.job_post_id == obj.id)
            .all()
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

    def update(self, entity: entities.JobPost) -> None:
        obj = self.db.get(JobPostModel, entity.id)
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

    def add_tag(self, job_post_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        if self.db.get(JobPostTag, (job_post_id, tag_id)) is not None:
            return
        self.db.add(JobPostTag(job_post_id=job_post_id, tag_id=tag_id))

    def remove_tag(self, job_post_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        row = self.db.get(JobPostTag, (job_post_id, tag_id))
        if row is not None:
            self.db.delete(row)

    def add_exclusion(
        self, job_post_id: uuid.UUID, excluded_job_post_id: uuid.UUID
    ) -> None:
        existing = self.db.get(JobPostExclusion, (job_post_id, excluded_job_post_id))
        if existing is not None:
            return
        self.db.add(
            JobPostExclusion(
                job_post_id=job_post_id, excluded_job_post_id=excluded_job_post_id
            )
        )

    def remove_exclusion(
        self, job_post_id: uuid.UUID, excluded_job_post_id: uuid.UUID
    ) -> None:
        row = self.db.get(JobPostExclusion, (job_post_id, excluded_job_post_id))
        if row is not None:
            self.db.delete(row)
