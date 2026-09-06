import uuid

from fastapi import APIRouter, Depends

from app.domains.assessments.attempts.dependencies import get_assessment_service
from app.domains.assessments.attempts.schemas import (
    AssessmentAnswerOut,
    AssessmentAttemptOut,
    AttemptDetailOut,
    CurrentQuestionOut,
    ReopenAttemptRequest,
    SubmitAnswerRequest,
)
from app.domains.assessments.attempts.service import AssessmentService
from app.domains.auth import entities as auth_entities
from app.domains.auth.dependencies import get_current_user
from app.domains.rbac.dependencies import require_permission

_manage_applications = Depends(require_permission("manage_applications"))

router = APIRouter(prefix="/assessment-attempts", tags=["assessments"])


@router.get("/{attempt_id}", response_model=AttemptDetailOut)
async def get_attempt(
    attempt_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
) -> AttemptDetailOut:
    detail = await service.get_attempt_detail(attempt_id, current_user)
    attempt = detail.attempt
    return AttemptDetailOut(
        id=attempt.id,
        application_id=attempt.application_id,
        template_type=attempt.template_type,
        template_id=attempt.template_id,
        status=attempt.status,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        template_title=detail.template_title,
        template_instructions=detail.template_instructions,
        time_limit_minutes=detail.time_limit_minutes,
        total_questions=detail.total_questions,
        answered_count=detail.answered_count,
        current_question=(
            CurrentQuestionOut.model_validate(detail.current_question)
            if detail.current_question is not None
            else None
        ),
        current_question_started_at=(
            detail.current_answer.question_started_at
            if detail.current_answer is not None
            else None
        ),
        current_answer_value=(
            detail.current_answer.answer_value
            if detail.current_answer is not None
            else None
        ),
    )


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
