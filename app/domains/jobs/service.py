import uuid
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app.core.unit_of_work import UnitOfWork
from app.domains.jobs import entities
from app.domains.jobs.exceptions import (
    CompanyAddressNotFoundError,
    JobPostNotFoundError,
    PositionNotFoundError,
    ResourceInUseError,
    TagNotFoundError,
)
from app.domains.jobs.repository import (
    CompanyAddressRepository,
    JobPostRepository,
    PositionRepository,
    TagRepository,
)


class CompanyAddressService:
    def __init__(self, addresses: CompanyAddressRepository, uow: UnitOfWork):
        self.addresses = addresses
        self.uow = uow

    def create(
        self,
        *,
        label: str,
        line1: str,
        line2: str | None,
        city: str,
        state_province: str | None,
        postal_code: str | None,
        country: str,
        latitude: Decimal | None,
        longitude: Decimal | None,
    ) -> entities.CompanyAddress:
        address_id = uuid.uuid4()
        self.addresses.add(
            entities.CompanyAddress(
                id=address_id,
                label=label,
                line1=line1,
                line2=line2,
                city=city,
                state_province=state_province,
                postal_code=postal_code,
                country=country,
                latitude=latitude,
                longitude=longitude,
            )
        )
        self.uow.commit()
        return self.addresses.get_by_id(address_id)

    def get(self, address_id: uuid.UUID) -> entities.CompanyAddress:
        address = self.addresses.get_by_id(address_id)
        if address is None:
            raise CompanyAddressNotFoundError(
                f"Company address '{address_id}' not found"
            )
        return address

    def list(self) -> list[entities.CompanyAddress]:
        return self.addresses.list_all()

    def update(
        self,
        address_id: uuid.UUID,
        *,
        label: str,
        line1: str,
        line2: str | None,
        city: str,
        state_province: str | None,
        postal_code: str | None,
        country: str,
        latitude: Decimal | None,
        longitude: Decimal | None,
    ) -> entities.CompanyAddress:
        self.get(address_id)
        self.addresses.update(
            entities.CompanyAddress(
                id=address_id,
                label=label,
                line1=line1,
                line2=line2,
                city=city,
                state_province=state_province,
                postal_code=postal_code,
                country=country,
                latitude=latitude,
                longitude=longitude,
            )
        )
        self.uow.commit()
        return self.addresses.get_by_id(address_id)

    def delete(self, address_id: uuid.UUID) -> None:
        self.get(address_id)
        self.addresses.delete(address_id)
        try:
            self.uow.commit()
        except IntegrityError:
            self.uow.rollback()
            raise ResourceInUseError(
                f"Company address '{address_id}' is still referenced by one or "
                "more job posts"
            ) from None


class PositionService:
    def __init__(self, positions: PositionRepository, uow: UnitOfWork):
        self.positions = positions
        self.uow = uow

    def create(self, *, title: str, description: str | None) -> entities.Position:
        position_id = uuid.uuid4()
        self.positions.add(
            entities.Position(id=position_id, title=title, description=description)
        )
        self.uow.commit()
        return self.positions.get_by_id(position_id)

    def get(self, position_id: uuid.UUID) -> entities.Position:
        position = self.positions.get_by_id(position_id)
        if position is None:
            raise PositionNotFoundError(f"Position '{position_id}' not found")
        return position

    def list(self) -> list[entities.Position]:
        return self.positions.list_all()

    def update(
        self, position_id: uuid.UUID, *, title: str, description: str | None
    ) -> entities.Position:
        self.get(position_id)
        self.positions.update(
            entities.Position(id=position_id, title=title, description=description)
        )
        self.uow.commit()
        return self.positions.get_by_id(position_id)

    def delete(self, position_id: uuid.UUID) -> None:
        self.get(position_id)
        self.positions.delete(position_id)
        try:
            self.uow.commit()
        except IntegrityError:
            self.uow.rollback()
            raise ResourceInUseError(
                f"Position '{position_id}' is still referenced by one or more "
                "job posts"
            ) from None


class TagService:
    def __init__(self, tags: TagRepository, uow: UnitOfWork):
        self.tags = tags
        self.uow = uow

    def create(self, *, name: str, description: str | None) -> entities.Tag:
        tag_id = uuid.uuid4()
        self.tags.add(entities.Tag(id=tag_id, name=name, description=description))
        self.uow.commit()
        return self.tags.get_by_id(tag_id)

    def get(self, tag_id: uuid.UUID) -> entities.Tag:
        tag = self.tags.get_by_id(tag_id)
        if tag is None:
            raise TagNotFoundError(f"Tag '{tag_id}' not found")
        return tag

    def list(self) -> list[entities.Tag]:
        return self.tags.list_all()

    def update(
        self, tag_id: uuid.UUID, *, name: str, description: str | None
    ) -> entities.Tag:
        self.get(tag_id)
        self.tags.update(entities.Tag(id=tag_id, name=name, description=description))
        self.uow.commit()
        return self.tags.get_by_id(tag_id)

    def delete(self, tag_id: uuid.UUID) -> None:
        self.get(tag_id)
        self.tags.delete(tag_id)
        try:
            self.uow.commit()
        except IntegrityError:
            self.uow.rollback()
            raise ResourceInUseError(
                f"Tag '{tag_id}' is still referenced by one or more job posts"
            ) from None


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

    def _require_position(self, position_id: uuid.UUID) -> entities.Position:
        position = self.positions.get_by_id(position_id)
        if position is None:
            raise PositionNotFoundError(f"Position '{position_id}' not found")
        return position

    def _require_address(
        self, company_address_id: uuid.UUID
    ) -> entities.CompanyAddress:
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
