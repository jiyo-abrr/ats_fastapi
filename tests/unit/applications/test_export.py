import io
import uuid
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace

from app.domains.applications.export import build_evaluation_pack


def _job():
    return SimpleNamespace(
        id=uuid.uuid4(),
        job_title="Senior Backend Engineer",
        position_title="Backend Engineer",
        employment_type="full_time",
        status="published",
        currency="PHP",
        salary_min=80000,
        salary_max=120000,
        description="Build APIs.",
        requirements="Python, Postgres.",
        qualifications="CS degree or equivalent.",
    )


def _row(first="Ana", last="Reyes"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        applicant_first_name=first,
        applicant_last_name=last,
        applicant_email=f"{first.lower()}@example.com",
        status="applied",
        created_at=datetime.now(UTC),
    )


def _open(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


def test_pack_has_job_rubric_and_manifest():
    data = build_evaluation_pack(job=_job(), applicants=[])
    names = _open(data).namelist()
    assert "job/description.md" in names
    assert "evaluation-rubric.md" in names
    assert "manifest.json" in names
    assert "README.md" in names
    assert "RESULTS-FORMAT.md" in names
    assert "evaluation-results.template.json" in names


def test_results_template_has_job_id_and_one_stub_per_applicant():
    import json

    job = _job()
    data = build_evaluation_pack(
        job=job,
        applicants=[
            {"row": _row("Ana", "Reyes"), "resume": None, "reviews": []},
            {"row": _row("Bo", "Cruz"), "resume": None, "reviews": []},
        ],
    )
    tpl = json.loads(_open(data).read("evaluation-results.template.json").decode())
    assert tpl["job_post_id"] == str(job.id)
    assert len(tpl["evaluations"]) == 2
    assert len(tpl["evaluations"][0]["resume_scores"]) == 9


def test_applicant_with_resume_and_reviews():
    row = _row()
    reviews = [
        {
            "template_type": "pre_assessment",
            "template_title": "Pre-Screen",
            "status": "completed",
            "answered_count": 1,
            "total_questions": 1,
            "completed_at": None,
            "questions": [
                {
                    "prompt": "Willing to work onsite?",
                    "question_type": "boolean",
                    "answer_value": True,
                }
            ],
        }
    ]
    data = build_evaluation_pack(
        job=_job(),
        applicants=[
            {"row": row, "resume": (b"%PDF-1.4", "resume.pdf"), "reviews": reviews}
        ],
    )
    zf = _open(data)
    names = zf.namelist()
    assert "applicants/01-ana-reyes/resume.pdf" in names
    body = zf.read("applicants/01-ana-reyes/assessments.md").decode()
    assert "Willing to work onsite?" in body
    assert "Yes" in body


def test_missing_resume_writes_placeholder():
    data = build_evaluation_pack(
        job=_job(),
        applicants=[{"row": _row("Bo", "Cruz"), "resume": None, "reviews": []}],
    )
    names = _open(data).namelist()
    assert "applicants/01-bo-cruz/RESUME-NOT-AVAILABLE.txt" in names
