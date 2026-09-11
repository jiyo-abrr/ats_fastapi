import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.domains.evaluations import entities
from app.domains.evaluations.exceptions import (
    EmptyEvaluationImportError,
    EvaluationNotFoundError,
)
from app.domains.evaluations.schemas import ApplicationEvaluationIn, EvaluationImportIn
from app.domains.evaluations.service import EvaluationService


def make_service():
    evaluations = AsyncMock()
    uow = AsyncMock()
    return EvaluationService(evaluations, uow), evaluations, uow


class TestImportResults:
    async def test_rejects_empty_payload(self):
        service, _evaluations, _uow = make_service()
        with pytest.raises(EmptyEvaluationImportError):
            await service.import_results(
                EvaluationImportIn(job_post_id=uuid.uuid4(), evaluations=[]),
                imported_by_user_id=uuid.uuid4(),
            )

    async def test_skips_applications_not_on_this_job_post(self):
        service, evaluations, uow = make_service()
        job_post_id = uuid.uuid4()
        stray_id = uuid.uuid4()
        evaluations.valid_application_ids.return_value = set()

        result = await service.import_results(
            EvaluationImportIn(
                job_post_id=job_post_id,
                evaluations=[
                    ApplicationEvaluationIn(
                        application_id=stray_id, recommendation="advance"
                    )
                ],
            ),
            imported_by_user_id=uuid.uuid4(),
        )

        assert result.imported == 0
        assert result.skipped == [str(stray_id)]
        evaluations.add.assert_not_called()
        uow.commit.assert_called_once()

    async def test_skips_a_fully_blank_row(self):
        service, evaluations, uow = make_service()
        app_id = uuid.uuid4()
        evaluations.valid_application_ids.return_value = {app_id}

        result = await service.import_results(
            EvaluationImportIn(
                job_post_id=uuid.uuid4(),
                evaluations=[ApplicationEvaluationIn(application_id=app_id)],
            ),
            imported_by_user_id=uuid.uuid4(),
        )

        assert result.imported == 0
        assert result.skipped == [str(app_id)]
        evaluations.add.assert_not_called()

    async def test_stores_one_evaluation_per_valid_application(self):
        service, evaluations, uow = make_service()
        app_id = uuid.uuid4()
        importer_id = uuid.uuid4()
        evaluations.valid_application_ids.return_value = {app_id}

        result = await service.import_results(
            EvaluationImportIn(
                job_post_id=uuid.uuid4(),
                model="gpt-5",
                rubric_version="1",
                evaluations=[
                    ApplicationEvaluationIn(
                        application_id=app_id,
                        recommendation="advance",
                        fit_score=80,
                        resume_scores=[
                            {
                                "dimension": "relevant_work_experience",
                                "rating": "strong",
                            }
                        ],
                    )
                ],
            ),
            imported_by_user_id=importer_id,
        )

        assert result.imported == 1
        assert result.skipped == []
        evaluations.add.assert_called_once()
        staged = evaluations.add.call_args[0][0]
        assert staged.application_id == app_id
        assert staged.imported_by_user_id == importer_id
        assert staged.model == "gpt-5"
        assert len(staged.scores) == 1
        assert staged.scores[0].category == "resume"
        uow.commit.assert_called_once()


class TestGetForApplication:
    async def test_raises_when_nothing_imported(self):
        service, evaluations, _uow = make_service()
        evaluations.get_latest.return_value = None
        with pytest.raises(EvaluationNotFoundError):
            await service.get_for_application(uuid.uuid4())

    async def test_returns_the_latest_evaluation(self):
        service, evaluations, _uow = make_service()
        app_id = uuid.uuid4()
        entity = entities.ApplicationEvaluation(
            id=uuid.uuid4(),
            application_id=app_id,
            imported_by_user_id=uuid.uuid4(),
            recommendation="advance",
            created_at=datetime.now(UTC),
        )
        evaluations.get_latest.return_value = entity

        out = await service.get_for_application(app_id)

        assert out.application_id == app_id
        assert out.recommendation == "advance"
