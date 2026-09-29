"""HTTP and worker exports prepare the same eligible applicants."""

import io
import json
import uuid
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from app.domains.auth.dependencies import get_current_user
from app.domains.auth.repository import UserRepository
from app.main import app
from app.workers.evaluation_export import _run_export
from tests.integration.factories import make_application, make_job_post, make_user


def exported_ids(payload):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        template = json.loads(archive.read("evaluation-results.template.json"))
        return {r["application_id"] for r in template["evaluations"]}


async def test_http_and_worker_share_export_selection(client, db_session):
    job = await make_job_post(db_session)
    hr = await make_user(db_session, role="hr")
    included = None
    for status, assessed in [
        ("applied", False),
        ("withdrawn", False),
        ("interview", True),
    ]:
        applicant = await make_user(db_session)
        row = await make_application(
            db_session, job_post=job, applicant=applicant, status=status
        )
        row.hr_assessed = assessed
        if status == "applied":
            included = row.id
    await db_session.commit()
    user = await UserRepository(db_session).get_by_id(hr.id)

    async def current_user():
        return user

    app.dependency_overrides[get_current_user] = current_user
    try:
        with patch(
            "app.domains.applications.service.get_object",
            return_value=(b"%PDF", "application/pdf"),
        ):
            response = await client.get(
                "/api/v1/applications/export", params={"job_post_id": str(job.id)}
            )
        assert response.status_code == 200, response.text
        assert exported_ids(response.content) == {str(included)}
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    export_job = SimpleNamespace(
        id=uuid.uuid4(), job_post_id=job.id, status_filter=None
    )
    with (
        patch(
            "app.workers.evaluation_export.get_object",
            return_value=(b"%PDF", "application/pdf"),
        ),
        patch("app.workers.evaluation_export.upload_object") as upload,
    ):
        key = await _run_export(db_session, export_job)
    assert key == f"evaluation_packs/{export_job.id}.zip"
    assert exported_ids(upload.call_args.args[2]) == {str(included)}
