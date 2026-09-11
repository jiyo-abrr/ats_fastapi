from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.evaluations.export_jobs import (
    EvaluationExportJobRepository,
    ExportJobService,
)
from app.domains.evaluations.repository import EvaluationRepository
from app.domains.evaluations.service import EvaluationService


def get_evaluation_repository(
    db: AsyncSession = Depends(get_db),
) -> EvaluationRepository:
    return EvaluationRepository(db)


def get_evaluation_service(
    evaluations: EvaluationRepository = Depends(get_evaluation_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> EvaluationService:
    return EvaluationService(evaluations, uow)


def get_evaluation_export_job_repository(
    db: AsyncSession = Depends(get_db),
) -> EvaluationExportJobRepository:
    return EvaluationExportJobRepository(db)


def get_export_job_service(
    jobs: EvaluationExportJobRepository = Depends(get_evaluation_export_job_repository),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> ExportJobService:
    return ExportJobService(jobs, uow)
