import uuid

from fastapi import APIRouter, Depends

from app.domains.assessments.dependencies import get_assessment_service
from app.domains.assessments.schemas import (
    AssessmentAnswerOut,
    AssessmentAttemptOut,
    ReopenAttemptRequest,
    SubmitAnswerRequest,
)
from app.domains.assessments.service import AssessmentService
from app.domains.auth import entities as auth_entities
from app.domains.auth.dependencies import get_current_user
from app.domains.rbac.dependencies import require_permission

_manage_applications = Depends(require_permission("manage_applications"))

router = APIRouter(prefix="/assessment-attempts", tags=["assessments"])


@router.post(
    "/{attempt_id}/questions/{question_id}/start", response_model=AssessmentAnswerOut
)
async def start_question(
    attempt_id: uuid.UUID,
    question_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
) -> AssessmentAnswerOut:
    return await service.start_question(attempt_id, question_id, current_user)


@router.post(
    "/{attempt_id}/questions/{question_id}/answer", response_model=AssessmentAttemptOut
)
async def submit_answer(
    attempt_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: SubmitAnswerRequest,
    current_user: auth_entities.User = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
) -> AssessmentAttemptOut:
    return await service.submit_answer(
        attempt_id, question_id, payload.answer_value, current_user
    )


@router.post(
    "/{attempt_id}/reopen",
    response_model=AssessmentAttemptOut,
    dependencies=[_manage_applications],
)
async def reopen_attempt(
    attempt_id: uuid.UUID,
    payload: ReopenAttemptRequest,
    current_user: auth_entities.User = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
) -> AssessmentAttemptOut:
    return await service.reopen(
        attempt_id, reason=payload.reason, current_user=current_user
    )
