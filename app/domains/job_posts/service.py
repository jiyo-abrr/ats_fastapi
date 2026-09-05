import uuid
from decimal import Decimal

from app.core.unit_of_work import UnitOfWork
from app.domains.company_addresses import entities as address_entities
from app.domains.company_addresses.exceptions import CompanyAddressNotFoundError
from app.domains.company_addresses.repository import CompanyAddressRepository
from app.domains.job_posts import entities
from app.domains.job_posts.exceptions import JobPostNotFoundError
from app.domains.job_posts.repository import JobPostRepository
from app.domains.positions import entities as position_entities
from app.domains.positions.exceptions import PositionNotFoundError
from app.domains.positions.repository import PositionRepository
from app.domains.tags.exceptions import TagNotFoundError
from app.domains.tags.repository import TagRepository


class JobPostService:
    def __init__(
        self,
        job_posts: JobPostRepository,
        positions: PositionRepository,
        addresses: CompanyAddressRepository,
        tags: TagRepository,
        uow: UnitOfWork,
    ):
        self.job_posts = job_posts
        self.positions = positions
        self.addresses = addresses
        self.tags = tags
        self.uow = uow

    def _require_position(self, position_id: uuid.UUID) -> position_entities.Position:
        position = self.positions.get_by_id(position_id)
        if position is None:
            raise PositionNotFoundError(f"Position '{position_id}' not found")
        return position

    def _require_address(
        self, company_address_id: uuid.UUID
    ) -> address_entities.CompanyAddress:
        address = self.addresses.get_by_id(company_address_id)
        if address is None:
            raise CompanyAddressNotFoundError(
                f"Company address '{company_address_id}' not found"
            )
        return address

    def get(self, job_post_id: uuid.UUID) -> entities.JobPost:
        job_post = self.job_posts.get_by_id(job_post_id)
        if job_post is None:
            raise JobPostNotFoundError(f"Job post '{job_post_id}' not found")
        return job_post

    def list(self) -> list[entities.JobPost]:
        return self.job_posts.list_all()

    def create(
        self,
        *,
        job_title: str,
        description: str,
        requirements: str,
        qualifications: str,
        salary_min: Decimal | None,
        salary_max: Decimal | None,
        employment_type: str,
        status: str,
        company_address_id: uuid.UUID,
        position_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
        excluded_job_post_ids: list[uuid.UUID],
    ) -> entities.JobPost:
        address = self._require_address(company_address_id)
        position = self._require_position(position_id)
        for tag_id in tag_ids:
            if self.tags.get_by_id(tag_id) is None:
                raise TagNotFoundError(f"Tag '{tag_id}' not found")
        for excluded_id in excluded_job_post_ids:
            self.get(excluded_id)

        job_post_id = uuid.uuid4()
        self.job_posts.add(
            entities.JobPost(
                id=job_post_id,
                job_title=job_title,
                description=description,
                requirements=requirements,
                qualifications=qualifications,
                salary_min=salary_min,
                salary_max=salary_max,
                employment_type=employment_type,
                status=status,
                company_address_id=company_address_id,
                company_address_label=address.label,
                position_id=position_id,
                position_title=position.title,
            )
        )
        # Flush before staging tag/exclusion rows: they reference job_posts.id
        # by plain FK (no ORM relationship), so SQLAlchemy won't otherwise know
        # to order the JobPost INSERT before them within the same flush.
        self.uow.flush()

        for tag_id in tag_ids:
            self.job_posts.add_tag(job_post_id, tag_id)
        for excluded_id in excluded_job_post_ids:
            self.job_posts.add_exclusion(job_post_id, excluded_id)

        self.uow.commit()
        return self.job_posts.get_by_id(job_post_id)

    def update(
        self,
        job_post_id: uuid.UUID,
        *,
        job_title: str,
        description: str,
        requirements: str,
        qualifications: str,
        salary_min: Decimal | None,
        salary_max: Decimal | None,
        employment_type: str,
        status: str,
        company_address_id: uuid.UUID,
        position_id: uuid.UUID,
    ) -> entities.JobPost:
        self.get(job_post_id)
        address = self._require_address(company_address_id)
        position = self._require_position(position_id)

        self.job_posts.update(
            entities.JobPost(
                id=job_post_id,
                job_title=job_title,
                description=description,
                requirements=requirements,
                qualifications=qualifications,
                salary_min=salary_min,
                salary_max=salary_max,
                employment_type=employment_type,
                status=status,
                company_address_id=company_address_id,
                company_address_label=address.label,
                position_id=position_id,
                position_title=position.title,
            )
        )
        self.uow.commit()
        return self.job_posts.get_by_id(job_post_id)

    def delete(self, job_post_id: uuid.UUID) -> None:
        self.get(job_post_id)
        self.job_posts.delete(job_post_id)
        self.uow.commit()

    def add_tag(self, job_post_id: uuid.UUID, tag_id: uuid.UUID) -> entities.JobPost:
        self.get(job_post_id)
        if self.tags.get_by_id(tag_id) is None:
            raise TagNotFoundError(f"Tag '{tag_id}' not found")
        self.job_posts.add_tag(job_post_id, tag_id)
        self.uow.commit()
        return self.job_posts.get_by_id(job_post_id)

    def remove_tag(
        self, job_post_id: uuid.UUID, tag_id: uuid.UUID
    ) -> entities.JobPost:
        self.get(job_post_id)
        self.job_posts.remove_tag(job_post_id, tag_id)
        self.uow.commit()
        return self.job_posts.get_by_id(job_post_id)

    def add_exclusion(
        self, job_post_id: uuid.UUID, excluded_job_post_id: uuid.UUID
    ) -> entities.JobPost:
        self.get(job_post_id)
        self.get(excluded_job_post_id)
        self.job_posts.add_exclusion(job_post_id, excluded_job_post_id)
        self.uow.commit()
        return self.job_posts.get_by_id(job_post_id)

    def remove_exclusion(
        self, job_post_id: uuid.UUID, excluded_job_post_id: uuid.UUID
    ) -> entities.JobPost:
        self.get(job_post_id)
        self.job_posts.remove_exclusion(job_post_id, excluded_job_post_id)
        self.uow.commit()
        return self.job_posts.get_by_id(job_post_id)
