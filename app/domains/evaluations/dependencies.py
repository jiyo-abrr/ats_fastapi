from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.evaluations.service import EvaluationService


def get_evaluation_service(
    db: AsyncSession = Depends(get_db),
) -> EvaluationService:
    return EvaluationService(db)
