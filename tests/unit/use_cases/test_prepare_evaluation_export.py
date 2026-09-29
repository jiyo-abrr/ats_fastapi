import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.domains.applications.enums import EVALUATION_ELIGIBLE_STATUSES
from app.domains.job_posts.exceptions import JobPostNotFoundError
from app.use_cases.prepare_evaluation_export import (
    ExportLimitExceeded,
    ExportPolicy,
    PrepareEvaluationExport,
)


def make_case(rows):
    exports, jobs, assessments = AsyncMock(), AsyncMock(), AsyncMock()
    jobs.get_by_id.return_value = SimpleNamespace(job_title="Engineer")
    exports.applicants.return_value = rows
    assessments.list_review_for_application.return_value = []
    return PrepareEvaluationExport(exports, jobs, assessments)


@pytest.mark.parametrize("statuses", [None, ["withdrawn"]])
async def test_export_preparation_shares_filters_and_handles_missing_resumes(statuses):
    rows = [SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())]
    case = make_case(rows)
    loader = AsyncMock(side_effect=[(b"resume", "resume.pdf"), None])
    job_id = uuid.uuid4()
    with patch(
        "app.use_cases.prepare_evaluation_export.build_evaluation_pack",
        return_value=b"zip",
    ) as build:
        result = await case.execute(
            job_id,
            statuses=statuses,
            policy=ExportPolicy(10, 100),
            load_resume=loader,
        )
    case.exports.applicants.assert_awaited_once_with(
        job_id,
        statuses=statuses or EVALUATION_ELIGIBLE_STATUSES,
        limit=11,
    )
    assert result.payload == b"zip"
    assert result.job_title == "Engineer"
    applicants = build.call_args.kwargs["applicants"]
    assert applicants[0]["resume"] == (b"resume", "resume.pdf")
    assert applicants[1]["resume"] is None
    assert case.assessments.list_review_for_application.await_count == 2


async def test_count_limit_fails_before_loading_resumes():
    case = make_case([SimpleNamespace(id=uuid.uuid4()) for _ in range(3)])
    loader = AsyncMock()
    with pytest.raises(ExportLimitExceeded, match="More than 2"):
        await case.execute(
            uuid.uuid4(), statuses=None, policy=ExportPolicy(2), load_resume=loader
        )
    loader.assert_not_awaited()


async def test_byte_limit_is_cumulative_and_stops_before_building_zip():
    case = make_case([SimpleNamespace(id=uuid.uuid4()) for _ in range(2)])
    loader = AsyncMock(return_value=(b"123", "r.pdf"))
    with patch(
        "app.use_cases.prepare_evaluation_export.build_evaluation_pack"
    ) as build:
        with pytest.raises(ExportLimitExceeded):
            await case.execute(
                uuid.uuid4(),
                statuses=None,
                policy=ExportPolicy(2, 5),
                load_resume=loader,
            )
    build.assert_not_called()


async def test_missing_job_does_not_load_applicants():
    case = make_case([])
    case.job_posts.get_by_id.return_value = None
    with pytest.raises(JobPostNotFoundError):
        await case.execute(
            uuid.uuid4(),
            statuses=None,
            policy=ExportPolicy(10),
            load_resume=AsyncMock(),
        )
    case.exports.applicants.assert_not_awaited()
