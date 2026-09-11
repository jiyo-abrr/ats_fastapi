import uuid
from unittest.mock import AsyncMock

import pytest

from app.core.queue import EVALUATION_EXPORT_QUEUE
from app.domains.evaluations.exceptions import EvaluationExportJobNotFoundError
from app.domains.evaluations.export_jobs import EvaluationExportJob, ExportJobService


def make_service():
    jobs = AsyncMock()
    uow = AsyncMock()
    return ExportJobService(jobs, uow), jobs, uow


class TestEnqueue:
    async def test_stages_creates_commits_and_publishes_to_rabbitmq(self):
        service, jobs, uow = make_service()
        broker = AsyncMock()
        job_post_id = uuid.uuid4()
        user_id = uuid.uuid4()

        result = await service.enqueue(
            job_post_id=job_post_id,
            requested_by_user_id=user_id,
            status_filter=["applied", "prescreening"],
            broker=broker,
        )

        jobs.create.assert_called_once()
        created_entity = jobs.create.call_args[0][0]
        assert created_entity.job_post_id == job_post_id
        assert created_entity.requested_by_user_id == user_id
        assert created_entity.status_filter == "applied,prescreening"
        assert created_entity.status == "pending"
        uow.commit.assert_called_once()
        broker.publish.assert_called_once_with(str(result.id), EVALUATION_EXPORT_QUEUE)

    async def test_no_status_filter_stored_as_none(self):
        service, jobs, uow = make_service()
        broker = AsyncMock()

        await service.enqueue(
            job_post_id=uuid.uuid4(),
            requested_by_user_id=uuid.uuid4(),
            status_filter=None,
            broker=broker,
        )

        created_entity = jobs.create.call_args[0][0]
        assert created_entity.status_filter is None


class TestGet:
    async def test_returns_job(self):
        service, jobs, _uow = make_service()
        job_id = uuid.uuid4()
        entity = EvaluationExportJob(
            id=job_id, job_post_id=uuid.uuid4(), requested_by_user_id=uuid.uuid4()
        )
        jobs.get_by_id.return_value = entity

        result = await service.get(job_id)

        assert result is entity

    async def test_raises_when_missing(self):
        service, jobs, _uow = make_service()
        jobs.get_by_id.return_value = None

        with pytest.raises(EvaluationExportJobNotFoundError):
            await service.get(uuid.uuid4())
