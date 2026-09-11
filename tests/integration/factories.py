"""Minimal ORM-level builders for integration tests — write rows directly,
like `app/scripts/seed_dummy_data.py`, so tests can set up state the API
can't reach."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.applications.models import Application
from app.domains.assessments.attempts.models import AssessmentAttempt
from app.domains.assessments.pre_assessment_templates.models import (
    PreAssessmentQuestion,
    PreAssessmentTemplate,
)
from app.domains.auth.models import User
from app.domains.company_addresses.models import CompanyAddress
from app.domains.job_posts.models import JobPost
from app.domains.positions.models import Position
from app.domains.rbac.models import Role


async def role_id(db: AsyncSession, name: str = "applicant") -> uuid.UUID:
    return (await db.execute(select(Role.id).where(Role.name == name))).scalar_one()


async def make_user(db: AsyncSession, *, role: str = "applicant", **kw) -> User:
    u = User(
        id=uuid.uuid4(),
        first_name=kw.get("first_name", "Test"),
        last_name=kw.get("last_name", "User"),
        contact_number="000",
        email=kw.get("email", f"{uuid.uuid4().hex[:12]}@example.com"),
        password_hash="x",
        role_id=await role_id(db, role),
        resume_object_key=kw.get("resume_object_key", "applicant_resume/x/r.pdf"),
    )
    db.add(u)
    await db.flush()
    return u


async def make_position(db: AsyncSession) -> Position:
    p = Position(id=uuid.uuid4(), title=f"Role {uuid.uuid4().hex[:6]}")
    db.add(p)
    await db.flush()
    return p


async def make_address(db: AsyncSession) -> CompanyAddress:
    a = CompanyAddress(
        id=uuid.uuid4(),
        label="HQ",
        line1="1 St",
        city="Manila",
        country="PH",
    )
    db.add(a)
    await db.flush()
    return a


async def make_job_post(
    db: AsyncSession, *, status: str = "published", **kw
) -> JobPost:
    jp = JobPost(
        id=uuid.uuid4(),
        job_title=kw.get("job_title", "Engineer"),
        description="d",
        requirements="r",
        qualifications="q",
        employment_type="full_time",
        status=status,
        company_address_id=(await make_address(db)).id,
        position_id=(await make_position(db)).id,
        assessment_window_days=kw.get("assessment_window_days", 4),
    )
    db.add(jp)
    await db.flush()
    return jp


async def make_application(
    db: AsyncSession,
    *,
    job_post: JobPost,
    applicant: User,
    status: str = "applied",
    **kw,
) -> Application:
    app = Application(
        id=uuid.uuid4(),
        job_post_id=job_post.id,
        applicant_id=applicant.id,
        status=status,
        resume_object_key="applicant_resume/x/r.pdf",
        assessment_deadline=kw.get("assessment_deadline"),
    )
    db.add(app)
    await db.flush()
    return app


async def make_pre_assessment_template(
    db: AsyncSession, *, questions: int = 1
) -> PreAssessmentTemplate:
    t = PreAssessmentTemplate(id=uuid.uuid4(), title="T")
    db.add(t)
    await db.flush()
    for i in range(questions):
        db.add(
            PreAssessmentQuestion(
                id=uuid.uuid4(),
                template_id=t.id,
                order_index=i,
                prompt=f"Q{i}",
                question_type="text",
            )
        )
    await db.flush()
    return t


async def make_attempt(
    db: AsyncSession,
    *,
    application: Application,
    template_id: uuid.UUID,
    template_type: str = "pre_assessment",
    status: str = "not_started",
) -> AssessmentAttempt:
    a = AssessmentAttempt(
        id=uuid.uuid4(),
        application_id=application.id,
        template_type=template_type,
        template_id=template_id,
        status=status,
    )
    db.add(a)
    await db.flush()
    return a
