import uuid

from app.core.repository import BaseRepository
from app.domains.jobs import entities
from app.domains.jobs.models import CompanyAddress as CompanyAddressModel
from app.domains.jobs.models import JobPost as JobPostModel
from app.domains.jobs.models import JobPostExclusion, JobPostTag
from app.domains.jobs.models import Position as PositionModel
from app.domains.jobs.models import Tag as TagModel


class CompanyAddressRepository(
    BaseRepository[CompanyAddressModel, entities.CompanyAddress, uuid.UUID]
):
    model = CompanyAddressModel

    def _to_entity(self, obj: CompanyAddressModel) -> entities.CompanyAddress:
        return entities.CompanyAddress(
            id=obj.id,
            label=obj.label,
            line1=obj.line1,
            line2=obj.line2,
            city=obj.city,
            state_province=obj.state_province,
            postal_code=obj.postal_code,
            country=obj.country,
            latitude=obj.latitude,
            longitude=obj.longitude,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    def _to_model(self, entity: entities.CompanyAddress) -> CompanyAddressModel:
        return CompanyAddressModel(
            id=entity.id,
            label=entity.label,
            line1=entity.line1,
            line2=entity.line2,
            city=entity.city,
            state_province=entity.state_province,
            postal_code=entity.postal_code,
            country=entity.country,
            latitude=entity.latitude,
            longitude=entity.longitude,
        )

    def update(self, entity: entities.CompanyAddress) -> None:
        obj = self.db.get(CompanyAddressModel, entity.id)
        if obj is None:
            return
        obj.label = entity.label
        obj.line1 = entity.line1
        obj.line2 = entity.line2
        obj.city = entity.city
        obj.state_province = entity.state_province
        obj.postal_code = entity.postal_code
        obj.country = entity.country
        obj.latitude = entity.latitude
        obj.longitude = entity.longitude


class PositionRepository(BaseRepository[PositionModel, entities.Position, uuid.UUID]):
    model = PositionModel

    def _to_entity(self, obj: PositionModel) -> entities.Position:
        return entities.Position(
            id=obj.id,
            title=obj.title,
            description=obj.description,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    def _to_model(self, entity: entities.Position) -> PositionModel:
        return PositionModel(
            id=entity.id, title=entity.title, description=entity.description
        )

    def update(self, entity: entities.Position) -> None:
        obj = self.db.get(PositionModel, entity.id)
        if obj is None:
            return
        obj.title = entity.title
        obj.description = entity.description


class TagRepository(BaseRepository[TagModel, entities.Tag, uuid.UUID]):
    model = TagModel

    def _to_entity(self, obj: TagModel) -> entities.Tag:
        return entities.Tag(id=obj.id, name=obj.name, description=obj.description)

    def _to_model(self, entity: entities.Tag) -> TagModel:
        return TagModel(id=entity.id, name=entity.name, description=entity.description)

    def get_by_name(self, name: str) -> entities.Tag | None:
        obj = self.db.query(TagModel).filter(TagModel.name == name).first()
        return self._to_entity(obj) if obj is not None else None

    def update(self, entity: entities.Tag) -> None:
        obj = self.db.get(TagModel, entity.id)
        if obj is None:
            return
        obj.name = entity.name
        obj.description = entity.description


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
            tags=[
                entities.Tag(id=t.id, name=t.name, description=t.description)
                for t in tags
            ],
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
