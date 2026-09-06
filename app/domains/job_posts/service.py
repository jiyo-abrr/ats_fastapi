import uuid
from decimal import Decimal

from app.core.unit_of_work import UnitOfWork
from app.domains.assessments.culture_fit_templates.exceptions import (
    CultureFitTemplateNotFoundError,
)
from app.domains.assessments.culture_fit_templates.repository import (
    CultureFitTemplateRepository,
)
from app.domains.assessments.pre_assessment_templates.exceptions import (
    PreAssessmentTemplateNotFoundError,
)
from app.domains.assessments.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)
from app.domains.assessments.technical_assessment_templates.exceptions import (
    TechnicalAssessmentTemplateNotFoundError,
)
from app.domains.assessments.technical_assessment_templates.repository import (
    TechnicalAssessmentTemplateRepository,
)
from app.domains.company_addresses import entities as address_entities
from app.domains.company_addresses.exceptions import CompanyAddressNotFoundError
from app.domains.company_addresses.repository import CompanyAddressRepository
from app.domains.job_posts import entities
from app.domains.job_posts.enums import JobPostStatus
from app.domains.job_posts.exceptions import (
    AssessmentTemplateAlreadyAttachedError,
    JobPostNotFoundError,
)
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
        pre_assessment_templates: PreAssessmentTemplateRepository,
        culture_fit_templates: CultureFitTemplateRepository,
        technical_assessment_templates: TechnicalAssessmentTemplateRepository,
        uow: UnitOfWork,
    ):
        self.job_posts = job_posts
        self.positions = positions
        self.addresses = addresses
        self.tags = tags
        self.pre_assessment_templates = pre_assessment_templates
        self.culture_fit_templates = culture_fit_templates
        self.technical_assessment_templates = technical_assessment_templates
        self.uow = uow

    async def _require_position(
        self, position_id: uuid.UUID
    ) -> position_entities.Position:
        position = await self.positions.get_by_id(position_id)
        if position is None:
            raise PositionNotFoundError(f"Position '{position_id}' not found")
        return position

    async def _require_address(
        self, company_address_id: uuid.UUID
    ) -> address_entities.CompanyAddress:
        address = await self.addresses.get_by_id(company_address_id)
        if address is None:
            raise CompanyAddressNotFoundError(
                f"Company address '{company_address_id}' not found"
            )
        return address

    async def get(self, job_post_id: uuid.UUID) -> entities.JobPost:
        job_post = await self.job_posts.get_by_id(job_post_id)
        if job_post is None:
            raise JobPostNotFoundError(f"Job post '{job_post_id}' not found")
        return job_post

    async def list(self) -> list[entities.JobPost]:
        return await self.job_posts.list_all()

    async def stats(self) -> dict[str, object]:
        """Zero-filled draft/published/closed tally for the ATS dashboard."""
        raw = await self.job_posts.status_counts()
        by_status = {s.value: raw.get(s.value, 0) for s in JobPostStatus}
        return {"by_status": by_status, "total": sum(by_status.values())}

    async def create(
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
        assessment_window_days: int = 4,
        pre_assessment_template_id: uuid.UUID | None = None,
        culture_fit_template_id: uuid.UUID | None = None,
        technical_assessment_template_id: uuid.UUID | None = None,
    ) -> entities.JobPost:
        address = await self._require_address(company_address_id)
        position = await self._require_position(position_id)
        for tag_id in tag_ids:
            if await self.tags.get_by_id(tag_id) is None:
                raise TagNotFoundError(f"Tag '{tag_id}' not found")
        for excluded_id in excluded_job_post_ids:
            await self.get(excluded_id)
        if (
            pre_assessment_template_id is not None
            and await self.pre_assessment_templates.get_by_id(
                pre_assessment_template_id
            )
            is None
        ):
            raise PreAssessmentTemplateNotFoundError(
                f"Pre-assessment template '{pre_assessment_template_id}' not found"
            )
        if (
            culture_fit_template_id is not None
            and await self.culture_fit_templates.get_by_id(culture_fit_template_id)
            is None
        ):
            raise CultureFitTemplateNotFoundError(
                f"Culture-fit template '{culture_fit_template_id}' not found"
            )
        if (
            technical_assessment_template_id is not None
            and await self.technical_assessment_templates.get_by_id(
                technical_assessment_template_id
            )
            is None
        ):
            raise TechnicalAssessmentTemplateNotFoundError(
                "Technical assessment template "
                f"'{technical_assessment_template_id}' not found"
            )

        job_post_id = uuid.uuid4()
        await self.job_posts.add(
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
                assessment_window_days=assessment_window_days,
            )
        )
        # Flush before staging tag/exclusion rows: they reference job_posts.id
        # by plain FK (no ORM relationship), so SQLAlchemy won't otherwise know
        # to order the JobPost INSERT before them within the same flush.
        await self.uow.flush()

        for tag_id in tag_ids:
            await self.job_posts.add_tag(job_post_id, tag_id)
        for excluded_id in excluded_job_post_ids:
            await self.job_posts.add_exclusion(job_post_id, excluded_id)
        if pre_assessment_template_id is not None:
            await self.job_posts.set_pre_assessment_template(
                job_post_id, pre_assessment_template_id
            )
        if culture_fit_template_id is not None:
            await self.job_posts.set_culture_fit_template(
                job_post_id, culture_fit_template_id
            )
        if technical_assessment_template_id is not None:
            await self.job_posts.set_technical_assessment_template(
                job_post_id, technical_assessment_template_id
            )

        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)

    async def update(
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
        assessment_window_days: int = 4,
    ) -> entities.JobPost:
        await self.get(job_post_id)
        address = await self._require_address(company_address_id)
        position = await self._require_position(position_id)

        await self.job_posts.update(
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
                assessment_window_days=assessment_window_days,
            )
        )
        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)

    async def delete(self, job_post_id: uuid.UUID) -> None:
        await self.get(job_post_id)
        await self.job_posts.delete(job_post_id)
        await self.uow.commit()

    async def add_tag(
        self, job_post_id: uuid.UUID, tag_id: uuid.UUID
    ) -> entities.JobPost:
        await self.get(job_post_id)
        if await self.tags.get_by_id(tag_id) is None:
            raise TagNotFoundError(f"Tag '{tag_id}' not found")
        await self.job_posts.add_tag(job_post_id, tag_id)
        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)

    async def remove_tag(
        self, job_post_id: uuid.UUID, tag_id: uuid.UUID
    ) -> entities.JobPost:
        await self.get(job_post_id)
        await self.job_posts.remove_tag(job_post_id, tag_id)
        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)

    async def add_exclusion(
        self, job_post_id: uuid.UUID, excluded_job_post_id: uuid.UUID
    ) -> entities.JobPost:
        await self.get(job_post_id)
        await self.get(excluded_job_post_id)
        await self.job_posts.add_exclusion(job_post_id, excluded_job_post_id)
        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)

    async def remove_exclusion(
        self, job_post_id: uuid.UUID, excluded_job_post_id: uuid.UUID
    ) -> entities.JobPost:
        await self.get(job_post_id)
        await self.job_posts.remove_exclusion(job_post_id, excluded_job_post_id)
        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)

    async def add_pre_assessment_template(
        self, job_post_id: uuid.UUID, template_id: uuid.UUID
    ) -> entities.JobPost:
        await self.get(job_post_id)
        if await self.pre_assessment_templates.get_by_id(template_id) is None:
            raise PreAssessmentTemplateNotFoundError(
                f"Pre-assessment template '{template_id}' not found"
            )
        if await self.job_posts.has_pre_assessment_template(job_post_id):
            raise AssessmentTemplateAlreadyAttachedError(
                f"Job post '{job_post_id}' already has a pre-assessment "
                "template attached"
            )
        await self.job_posts.set_pre_assessment_template(job_post_id, template_id)
        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)

    async def remove_pre_assessment_template(
        self, job_post_id: uuid.UUID
    ) -> entities.JobPost:
        await self.get(job_post_id)
        await self.job_posts.remove_pre_assessment_template(job_post_id)
        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)

    async def add_culture_fit_template(
        self, job_post_id: uuid.UUID, template_id: uuid.UUID
    ) -> entities.JobPost:
        await self.get(job_post_id)
        if await self.culture_fit_templates.get_by_id(template_id) is None:
            raise CultureFitTemplateNotFoundError(
                f"Culture-fit template '{template_id}' not found"
            )
        if await self.job_posts.has_culture_fit_template(job_post_id):
            raise AssessmentTemplateAlreadyAttachedError(
                f"Job post '{job_post_id}' already has a culture-fit "
                "template attached"
            )
        await self.job_posts.set_culture_fit_template(job_post_id, template_id)
        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)

    async def remove_culture_fit_template(
        self, job_post_id: uuid.UUID
    ) -> entities.JobPost:
        await self.get(job_post_id)
        await self.job_posts.remove_culture_fit_template(job_post_id)
        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)

    async def add_technical_assessment_template(
        self, job_post_id: uuid.UUID, template_id: uuid.UUID
    ) -> entities.JobPost:
        await self.get(job_post_id)
        if await self.technical_assessment_templates.get_by_id(template_id) is None:
            raise TechnicalAssessmentTemplateNotFoundError(
                f"Technical assessment template '{template_id}' not found"
            )
        if await self.job_posts.has_technical_assessment_template(job_post_id):
            raise AssessmentTemplateAlreadyAttachedError(
                f"Job post '{job_post_id}' already has a technical "
                "assessment template attached"
            )
        await self.job_posts.set_technical_assessment_template(
            job_post_id, template_id
        )
        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)

    async def remove_technical_assessment_template(
        self, job_post_id: uuid.UUID
    ) -> entities.JobPost:
        await self.get(job_post_id)
        await self.job_posts.remove_technical_assessment_template(job_post_id)
        await self.uow.commit()
        return await self.job_posts.get_by_id(job_post_id)
