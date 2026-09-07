"""Populate the database with a realistic set of dummy data for local
development and manual testing.

    uv run python -m app.scripts.seed_dummy_data          # seed (skip if seeded)
    uv run python -m app.scripts.seed_dummy_data --wipe   # reset, then re-seed

What it creates: HR + applicant users, positions, tags, company addresses,
one template of each assessment type (with questions), a spread of job posts
(published / draft / closed, some with templates attached, one exclusion
pair), applications across the whole status pipeline, and a few assessment
attempts (not started / in progress / completed / expired).

Notes:
- Every dummy user's password is ``Password123!``.
- ``role``/``permission`` rows and any ``admin`` user are never touched.
- Resumes are only referenced by key — nothing is uploaded to MinIO, so
  ``GET /applications/{id}/resume`` will 404 for seeded applications. That's
  expected; everything else works.
- Writes directly against the ORM models (not the domain services), so it
  can build states the API deliberately doesn't expose (e.g. a `disqualified`
  application, an `expired` attempt).
"""

import argparse
import asyncio
import selectors
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.models import (
    Application,
    AssessmentDeadlineExtension,
)
from app.domains.assessments.attempts.enums import AttemptStatus, TemplateType
from app.domains.assessments.attempts.models import (
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentAttemptReopen,
)
from app.domains.assessments.culture_fit_templates.models import (
    CultureFitQuestion,
    CultureFitTemplate,
)
from app.domains.assessments.pre_assessment_templates.models import (
    PreAssessmentQuestion,
    PreAssessmentTemplate,
)
from app.domains.assessments.technical_assessment_templates.models import (
    TechnicalAssessmentQuestion,
    TechnicalAssessmentTemplate,
)
from app.domains.auth.models import User
from app.domains.company_addresses.models import CompanyAddress
from app.domains.job_posts.enums import EmploymentType, JobPostStatus
from app.domains.job_posts.models import (
    JobPost,
    JobPostCultureFitTemplate,
    JobPostExclusion,
    JobPostPreAssessmentTemplate,
    JobPostTag,
    JobPostTechnicalAssessmentTemplate,
)
from app.domains.positions.models import Position
from app.domains.rbac.models import Role
from app.domains.tags.models import Tag

PASSWORD = "Password123!"  # noqa: S105 - dummy data only
SENTINEL_EMAIL = "hr1@example.com"

NOW = datetime.now(timezone.utc)


def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


async def already_seeded(db) -> bool:
    existing = await db.scalar(select(User).where(User.email == SENTINEL_EMAIL))
    return existing is not None


async def wipe(db) -> None:
    """Delete everything this script creates. Leaves roles/permissions and any
    non-applicant/non-hr (i.e. admin) users alone."""
    print("Wiping existing dummy data...")
    # Order matters: children before parents.
    await db.execute(delete(AssessmentAnswer))
    await db.execute(delete(AssessmentAttemptReopen))
    await db.execute(delete(AssessmentAttempt))
    await db.execute(delete(AssessmentDeadlineExtension))
    await db.execute(delete(Application))

    await db.execute(delete(JobPostTag))
    await db.execute(delete(JobPostExclusion))
    await db.execute(delete(JobPostPreAssessmentTemplate))
    await db.execute(delete(JobPostCultureFitTemplate))
    await db.execute(delete(JobPostTechnicalAssessmentTemplate))
    await db.execute(delete(JobPost))

    await db.execute(delete(PreAssessmentQuestion))
    await db.execute(delete(PreAssessmentTemplate))
    await db.execute(delete(CultureFitQuestion))
    await db.execute(delete(CultureFitTemplate))
    await db.execute(delete(TechnicalAssessmentQuestion))
    await db.execute(delete(TechnicalAssessmentTemplate))

    await db.execute(delete(Position))
    await db.execute(delete(Tag))
    await db.execute(delete(CompanyAddress))

    admin_role = await db.scalar(select(Role).where(Role.name == "admin"))
    await db.execute(delete(User).where(User.role_id != admin_role.id))
    await db.commit()


async def seed(db) -> None:
    roles = {r.name: r for r in (await db.execute(select(Role))).scalars().all()}
    if not {"admin", "hr", "applicant"} <= roles.keys():
        print(
            "Roles not seeded — run `uv run alembic upgrade head` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---- users -----------------------------------------------------------
    def make_user(first, last, email, role_name, *, resume=False):
        uid = uuid.uuid4()
        return User(
            id=uid,
            first_name=first,
            middle_initial=None,
            last_name=last,
            contact_number="+639171234567",
            email=email,
            password_hash=hash_password(PASSWORD),
            role_id=roles[role_name].id,
            resume_object_key=(
                f"applicant_resume/{uid}/dummy_resume.pdf" if resume else None
            ),
        )

    hr1 = make_user("Alice", "Reyes", "hr1@example.com", "hr")
    hr2 = make_user("Bob", "Santos", "hr2@example.com", "hr")
    applicants = [
        make_user(
            "Carla", "Mendoza", "applicant1@example.com", "applicant", resume=True
        ),
        make_user("Daniel", "Cruz", "applicant2@example.com", "applicant", resume=True),
        make_user("Erika", "Lim", "applicant3@example.com", "applicant", resume=True),
        make_user("Francis", "Tan", "applicant4@example.com", "applicant", resume=True),
        make_user(
            "Grace", "Villanueva", "applicant5@example.com", "applicant", resume=True
        ),
        make_user("Henry", "Dizon", "applicant6@example.com", "applicant", resume=True),
    ]
    db.add_all([hr1, hr2, *applicants])

    # ---- positions ------------------------------------------------------
    positions = {
        "swe": Position(
            id=uuid.uuid4(),
            title="Software Engineer",
            description="Builds and maintains application software.",
        ),
        "senior_swe": Position(
            id=uuid.uuid4(),
            title="Senior Software Engineer",
            description="Leads design and delivery of complex features.",
        ),
        "data_analyst": Position(
            id=uuid.uuid4(),
            title="Data Analyst",
            description="Turns raw data into decisions.",
        ),
        "pm": Position(
            id=uuid.uuid4(),
            title="Product Manager",
            description="Owns the product roadmap and priorities.",
        ),
        "qa": Position(
            id=uuid.uuid4(),
            title="QA Engineer",
            description="Designs and runs test plans.",
        ),
        "devops": Position(
            id=uuid.uuid4(),
            title="DevOps Engineer",
            description="Owns CI/CD and infrastructure.",
        ),
    }
    db.add_all(positions.values())

    # ---- tags ----------------------------------------------------------
    tag_names = [
        "Python",
        "FastAPI",
        "React",
        "PostgreSQL",
        "Docker",
        "AWS",
        "Remote",
        "Senior",
        "Junior",
        "Contract",
    ]
    tags = {
        n: Tag(id=uuid.uuid4(), name=n, description=f"{n} skill/attribute")
        for n in tag_names
    }
    db.add_all(tags.values())

    # ---- company addresses -------------------------------------------
    hq = CompanyAddress(
        id=uuid.uuid4(),
        label="Manila HQ",
        line1="1 Ayala Ave",
        line2="24th Floor",
        city="Makati",
        state_province="Metro Manila",
        postal_code="1226",
        country="Philippines",
        latitude=None,
        longitude=None,
    )
    cebu = CompanyAddress(
        id=uuid.uuid4(),
        label="Cebu Office",
        line1="Cebu IT Park",
        line2=None,
        city="Cebu City",
        state_province="Cebu",
        postal_code="6000",
        country="Philippines",
        latitude=None,
        longitude=None,
    )
    remote = CompanyAddress(
        id=uuid.uuid4(),
        label="Remote (PH)",
        line1="N/A",
        line2=None,
        city="N/A",
        state_province=None,
        postal_code=None,
        country="Philippines",
        latitude=None,
        longitude=None,
    )
    db.add_all([hq, cebu, remote])

    # ---- assessment templates --------------------------------------
    pre_tpl = PreAssessmentTemplate(
        id=uuid.uuid4(),
        title="General Pre-Screening",
        description="Baseline screening questions for all engineering roles.",
        instructions="Answer honestly. You have 30 minutes.",
        time_limit_minutes=30,
    )
    pre_qs = [
        PreAssessmentQuestion(
            id=uuid.uuid4(),
            template_id=pre_tpl.id,
            order_index=0,
            prompt="How many years of professional experience do you have?",
            question_type="number",
            config={"min": 0, "max": 50},
            time_limit_seconds=None,
        ),
        PreAssessmentQuestion(
            id=uuid.uuid4(),
            template_id=pre_tpl.id,
            order_index=1,
            prompt="Are you willing to work on-site at least 2 days a week?",
            question_type="boolean",
            config=None,
            time_limit_seconds=None,
        ),
        PreAssessmentQuestion(
            id=uuid.uuid4(),
            template_id=pre_tpl.id,
            order_index=2,
            prompt="What is your notice period?",
            question_type="single_choice",
            config={"options": ["Immediate", "2 weeks", "1 month", "2 months+"]},
            time_limit_seconds=None,
        ),
        PreAssessmentQuestion(
            id=uuid.uuid4(),
            template_id=pre_tpl.id,
            order_index=3,
            prompt="Briefly describe a project you are proud of.",
            question_type="long_text",
            config={"max_length": 2000},
            time_limit_seconds=None,
        ),
    ]

    cf_tpl = CultureFitTemplate(
        id=uuid.uuid4(),
        title="Culture Fit Survey",
        description="Values and working-style alignment.",
        instructions="Go with your first instinct. Each question is timed.",
        time_limit_minutes=20,
    )
    cf_qs = [
        CultureFitQuestion(
            id=uuid.uuid4(),
            template_id=cf_tpl.id,
            order_index=0,
            prompt="I prefer clear processes over improvisation.",
            question_type="rating",
            config={"min": 1, "max": 5},
            time_limit_seconds=120,
        ),
        CultureFitQuestion(
            id=uuid.uuid4(),
            template_id=cf_tpl.id,
            order_index=1,
            prompt="I do my best work when collaborating closely with others.",
            question_type="rating",
            config={"min": 1, "max": 5},
            time_limit_seconds=120,
        ),
        CultureFitQuestion(
            id=uuid.uuid4(),
            template_id=cf_tpl.id,
            order_index=2,
            prompt="Which best describes how you handle disagreement?",
            question_type="single_choice",
            config={
                "options": [
                    "Raise it directly",
                    "Escalate to a lead",
                    "Let it go",
                    "Discuss 1:1 first",
                ]
            },
            time_limit_seconds=120,
        ),
    ]

    tech_tpl = TechnicalAssessmentTemplate(
        id=uuid.uuid4(),
        title="Backend Technical",
        description="Practical backend engineering questions.",
        instructions="Pseudocode is fine. You have 60 minutes.",
        time_limit_minutes=60,
    )
    tech_qs = [
        TechnicalAssessmentQuestion(
            id=uuid.uuid4(),
            template_id=tech_tpl.id,
            order_index=0,
            prompt="Explain how you would design a rate limiter for an HTTP API.",
            question_type="long_text",
            config={"max_length": 4000},
            time_limit_seconds=None,
        ),
        TechnicalAssessmentQuestion(
            id=uuid.uuid4(),
            template_id=tech_tpl.id,
            order_index=1,
            prompt="Which Postgres index type best supports partial-match text search?",
            question_type="single_choice",
            config={"options": ["B-tree", "GIN", "Hash", "BRIN"]},
            time_limit_seconds=None,
        ),
        TechnicalAssessmentQuestion(
            id=uuid.uuid4(),
            template_id=tech_tpl.id,
            order_index=2,
            prompt="Write a SQL query returning the 2nd-highest salary per department.",
            question_type="long_text",
            config={"max_length": 2000},
            time_limit_seconds=None,
        ),
    ]

    # Questions have a plain FK to their template but no relationship(), so the
    # unit-of-work can't infer insert ordering — flush templates first.
    db.add_all([pre_tpl, cf_tpl, tech_tpl])
    await db.flush()
    db.add_all([*pre_qs, *cf_qs, *tech_qs])

    # ---- job posts ---------------------------------------------------
    def job(
        title,
        pos,
        addr,
        etype,
        status,
        tag_keys,
        *,
        salary=None,
        window=4,
        pre=False,
        cf=False,
        tech=False,
    ):
        jp = JobPost(
            id=uuid.uuid4(),
            job_title=title,
            description=f"We are hiring a {title}. Join a small, fast-moving team.",
            requirements=(
                "- Strong fundamentals\n- Clear communication\n- Ownership mindset"
            ),
            qualifications=(
                "- Relevant degree or equivalent experience\n- Portfolio or references"
            ),
            salary_min=salary[0] if salary else None,
            salary_max=salary[1] if salary else None,
            employment_type=etype.value,
            status=status.value,
            company_address_id=addr.id,
            position_id=pos.id,
            assessment_window_days=window,
        )
        return jp, tag_keys, pre, cf, tech

    specs = [
        job(
            "Senior Backend Engineer",
            positions["senior_swe"],
            hq,
            EmploymentType.FULL_TIME,
            JobPostStatus.PUBLISHED,
            ["Python", "FastAPI", "PostgreSQL", "Senior"],
            salary=(120000, 180000),
            window=5,
            pre=True,
            cf=True,
            tech=True,
        ),
        job(
            "Backend Engineer",
            positions["swe"],
            remote,
            EmploymentType.FULL_TIME,
            JobPostStatus.PUBLISHED,
            ["Python", "FastAPI", "Docker", "Remote"],
            salary=(80000, 120000),
            pre=True,
            tech=True,
        ),
        job(
            "Data Analyst",
            positions["data_analyst"],
            cebu,
            EmploymentType.FULL_TIME,
            JobPostStatus.PUBLISHED,
            ["PostgreSQL", "AWS"],
            salary=(60000, 90000),
            pre=True,
        ),
        job(
            "Product Manager",
            positions["pm"],
            hq,
            EmploymentType.FULL_TIME,
            JobPostStatus.PUBLISHED,
            ["Senior"],
            salary=(110000, 160000),
        ),
        job(
            "QA Engineer (Contract)",
            positions["qa"],
            remote,
            EmploymentType.CONTRACT,
            JobPostStatus.PUBLISHED,
            ["Contract", "Remote"],
            salary=(50000, 70000),
            cf=True,
        ),
        job(
            "Junior Frontend Developer",
            positions["swe"],
            hq,
            EmploymentType.FULL_TIME,
            JobPostStatus.DRAFT,
            ["React", "Junior"],
            salary=(40000, 60000),
        ),
        job(
            "DevOps Engineer",
            positions["devops"],
            remote,
            EmploymentType.FULL_TIME,
            JobPostStatus.CLOSED,
            ["AWS", "Docker", "Remote"],
            salary=(100000, 150000),
        ),
    ]
    job_posts = [s[0] for s in specs]
    db.add_all(job_posts)
    await db.flush()  # job_posts.id must exist before the join rows below

    for jp, tag_keys, pre, cf, tech in specs:
        for tk in tag_keys:
            db.add(JobPostTag(job_post_id=jp.id, tag_id=tags[tk].id))
        if pre:
            db.add(
                JobPostPreAssessmentTemplate(job_post_id=jp.id, template_id=pre_tpl.id)
            )
        if cf:
            db.add(JobPostCultureFitTemplate(job_post_id=jp.id, template_id=cf_tpl.id))
        if tech:
            db.add(
                JobPostTechnicalAssessmentTemplate(
                    job_post_id=jp.id, template_id=tech_tpl.id
                )
            )

    senior_be, backend, data_analyst, pm, qa_contract, junior_fe, devops = job_posts

    # "don't let applicants of the Backend Engineer role also apply to Senior Backend"
    db.add(JobPostExclusion(job_post_id=senior_be.id, excluded_job_post_id=backend.id))
    await db.flush()

    # ---- applications ---------------------------------------------
    a1, a2, a3, a4, a5, a6 = applicants

    def application(applicant, jp, status, *, applied_days_ago=10):
        applied_at = days_ago(applied_days_ago)
        return Application(
            id=uuid.uuid4(),
            job_post_id=jp.id,
            applicant_id=applicant.id,
            status=status.value,
            resume_object_key=applicant.resume_object_key,
            assessment_deadline=applied_at + timedelta(days=jp.assessment_window_days),
            created_at=applied_at,
        )

    apps = {
        "a1_senior": application(
            a1, senior_be, ApplicationStatus.PRESCREENING, applied_days_ago=12
        ),
        "a1_data": application(
            a1, data_analyst, ApplicationStatus.APPLIED, applied_days_ago=2
        ),
        "a2_backend": application(
            a2, backend, ApplicationStatus.INTERVIEW, applied_days_ago=20
        ),
        "a2_pm": application(a2, pm, ApplicationStatus.APPLIED, applied_days_ago=3),
        "a3_senior": application(
            a3, senior_be, ApplicationStatus.APPLIED, applied_days_ago=1
        ),
        "a3_pm": application(a3, pm, ApplicationStatus.DENIED, applied_days_ago=15),
        "a4_backend": application(
            a4, backend, ApplicationStatus.SUCCESS, applied_days_ago=30
        ),
        "a4_qa": application(
            a4, qa_contract, ApplicationStatus.APPLIED, applied_days_ago=4
        ),
        "a5_data": application(
            a5, data_analyst, ApplicationStatus.PRESCREENING, applied_days_ago=9
        ),
        "a5_pm": application(a5, pm, ApplicationStatus.INTERVIEW, applied_days_ago=18),
        "a6_qa": application(
            a6, qa_contract, ApplicationStatus.FAILED, applied_days_ago=25
        ),
        "a6_senior_withdrawn": application(
            a6, senior_be, ApplicationStatus.WITHDRAWN, applied_days_ago=22
        ),
        "a5_senior_disq": application(
            a5, senior_be, ApplicationStatus.DISQUALIFIED, applied_days_ago=14
        ),
    }
    # the disqualified one is past its (un-extended) deadline
    apps["a5_senior_disq"].assessment_deadline = days_ago(6)
    db.add_all(apps.values())
    await db.flush()

    # one deadline extension on the prescreening application
    db.add(
        AssessmentDeadlineExtension(
            id=uuid.uuid4(),
            application_id=apps["a1_senior"].id,
            extended_by_user_id=hr1.id,
            reason="Applicant requested extra time due to a family emergency.",
            previous_deadline=apps["a1_senior"].assessment_deadline,
            new_deadline=apps["a1_senior"].assessment_deadline + timedelta(days=3),
        )
    )
    apps["a1_senior"].assessment_deadline += timedelta(days=3)

    # ---- assessment attempts + answers --------------------------
    def attempt(app_row, ttype, tpl_id, status, *, started=None, completed=None):
        return AssessmentAttempt(
            id=uuid.uuid4(),
            application_id=app_row.id,
            template_type=ttype.value,
            template_id=tpl_id,
            status=status.value,
            started_at=started,
            completed_at=completed,
        )

    def answer(att, question, value, *, started, answered):
        return AssessmentAnswer(
            id=uuid.uuid4(),
            attempt_id=att.id,
            question_id=question.id,
            question_started_at=started,
            answered_at=answered,
            answer_value=value,
        )

    attempts = []
    answers = []

    # a1 / Senior Backend — all 3 attempts completed
    t0 = days_ago(11)
    pre_att = attempt(
        apps["a1_senior"],
        TemplateType.PRE_ASSESSMENT,
        pre_tpl.id,
        AttemptStatus.COMPLETED,
        started=t0,
        completed=t0 + timedelta(minutes=18),
    )
    cf_att = attempt(
        apps["a1_senior"],
        TemplateType.CULTURE_FIT,
        cf_tpl.id,
        AttemptStatus.COMPLETED,
        started=t0 + timedelta(hours=1),
        completed=t0 + timedelta(hours=1, minutes=9),
    )
    tech_att = attempt(
        apps["a1_senior"],
        TemplateType.TECHNICAL,
        tech_tpl.id,
        AttemptStatus.COMPLETED,
        started=t0 + timedelta(hours=2),
        completed=t0 + timedelta(hours=2, minutes=47),
    )
    attempts += [pre_att, cf_att, tech_att]
    answers += [
        answer(pre_att, pre_qs[0], 6, started=t0, answered=t0 + timedelta(minutes=1)),
        answer(
            pre_att,
            pre_qs[1],
            True,
            started=t0 + timedelta(minutes=1),
            answered=t0 + timedelta(minutes=2),
        ),
        answer(
            pre_att,
            pre_qs[2],
            "1 month",
            started=t0 + timedelta(minutes=2),
            answered=t0 + timedelta(minutes=3),
        ),
        answer(
            pre_att,
            pre_qs[3],
            "Built a real-time inventory sync service handling 5k events/sec.",
            started=t0 + timedelta(minutes=3),
            answered=t0 + timedelta(minutes=17),
        ),
        answer(
            cf_att,
            cf_qs[0],
            4,
            started=t0 + timedelta(hours=1),
            answered=t0 + timedelta(hours=1, minutes=1),
        ),
        answer(
            cf_att,
            cf_qs[1],
            5,
            started=t0 + timedelta(hours=1, minutes=1),
            answered=t0 + timedelta(hours=1, minutes=2),
        ),
        answer(
            cf_att,
            cf_qs[2],
            "Discuss 1:1 first",
            started=t0 + timedelta(hours=1, minutes=2),
            answered=t0 + timedelta(hours=1, minutes=3),
        ),
        answer(
            tech_att,
            tech_qs[0],
            "Token bucket in Redis keyed by client id; refill on read.",
            started=t0 + timedelta(hours=2),
            answered=t0 + timedelta(hours=2, minutes=20),
        ),
        answer(
            tech_att,
            tech_qs[1],
            "GIN",
            started=t0 + timedelta(hours=2, minutes=20),
            answered=t0 + timedelta(hours=2, minutes=25),
        ),
        answer(
            tech_att,
            tech_qs[2],
            "SELECT department_id, MAX(salary) ... window function DENSE_RANK.",
            started=t0 + timedelta(hours=2, minutes=25),
            answered=t0 + timedelta(hours=2, minutes=45),
        ),
    ]

    # a1 / Data Analyst — pre attempt in progress, 1 answer so far
    t1 = days_ago(1)
    pre_att2 = attempt(
        apps["a1_data"],
        TemplateType.PRE_ASSESSMENT,
        pre_tpl.id,
        AttemptStatus.IN_PROGRESS,
        started=t1,
    )
    attempts.append(pre_att2)
    answers.append(
        answer(pre_att2, pre_qs[0], 6, started=t1, answered=t1 + timedelta(minutes=2))
    )

    # a3 / Senior Backend — all 3 attempts not started
    attempts += [
        attempt(
            apps["a3_senior"],
            TemplateType.PRE_ASSESSMENT,
            pre_tpl.id,
            AttemptStatus.NOT_STARTED,
        ),
        attempt(
            apps["a3_senior"],
            TemplateType.CULTURE_FIT,
            cf_tpl.id,
            AttemptStatus.NOT_STARTED,
        ),
        attempt(
            apps["a3_senior"],
            TemplateType.TECHNICAL,
            tech_tpl.id,
            AttemptStatus.NOT_STARTED,
        ),
    ]

    # a4 / Backend (success) — pre + technical completed
    t2 = days_ago(29)
    pre_att3 = attempt(
        apps["a4_backend"],
        TemplateType.PRE_ASSESSMENT,
        pre_tpl.id,
        AttemptStatus.COMPLETED,
        started=t2,
        completed=t2 + timedelta(minutes=22),
    )
    tech_att3 = attempt(
        apps["a4_backend"],
        TemplateType.TECHNICAL,
        tech_tpl.id,
        AttemptStatus.COMPLETED,
        started=t2 + timedelta(hours=1),
        completed=t2 + timedelta(hours=1, minutes=55),
    )
    attempts += [pre_att3, tech_att3]
    answers += [
        answer(pre_att3, pre_qs[0], 4, started=t2, answered=t2 + timedelta(minutes=1)),
        answer(
            pre_att3,
            pre_qs[1],
            True,
            started=t2 + timedelta(minutes=1),
            answered=t2 + timedelta(minutes=2),
        ),
        answer(
            pre_att3,
            pre_qs[2],
            "2 weeks",
            started=t2 + timedelta(minutes=2),
            answered=t2 + timedelta(minutes=3),
        ),
        answer(
            pre_att3,
            pre_qs[3],
            "Migrated a monolith's auth to JWT with zero downtime.",
            started=t2 + timedelta(minutes=3),
            answered=t2 + timedelta(minutes=20),
        ),
        answer(
            tech_att3,
            tech_qs[0],
            "Fixed-window counter in Redis; INCR + EXPIRE.",
            started=t2 + timedelta(hours=1),
            answered=t2 + timedelta(hours=1, minutes=25),
        ),
        answer(
            tech_att3,
            tech_qs[1],
            "GIN",
            started=t2 + timedelta(hours=1, minutes=25),
            answered=t2 + timedelta(hours=1, minutes=30),
        ),
        answer(
            tech_att3,
            tech_qs[2],
            "Use DENSE_RANK() OVER (PARTITION BY dept ORDER BY salary DESC).",
            started=t2 + timedelta(hours=1, minutes=30),
            answered=t2 + timedelta(hours=1, minutes=50),
        ),
    ]

    # a6 / QA Contract (failed) — culture-fit attempt expired
    t3 = days_ago(24)
    cf_att2 = attempt(
        apps["a6_qa"],
        TemplateType.CULTURE_FIT,
        cf_tpl.id,
        AttemptStatus.EXPIRED,
        started=t3,
    )
    attempts.append(cf_att2)
    answers.append(
        answer(cf_att2, cf_qs[0], 3, started=t3, answered=t3 + timedelta(minutes=1))
    )

    # answers -> attempts is a plain FK, no relationship() — flush attempts first
    db.add_all(attempts)
    await db.flush()
    db.add_all(answers)

    await db.commit()

    print(
        "Seeded:\n"
        f"  users:         2 HR + {len(applicants)} applicants\n"
        f"  positions:     {len(positions)}\n"
        f"  tags:          {len(tags)}\n"
        "  company addrs: 3\n"
        "  templates:     1 pre-assessment, 1 culture-fit, 1 technical\n"
        f"  job posts:     {len(job_posts)} (5 published, 1 draft, 1 closed)\n"
        f"  applications:  {len(apps)} across the full status pipeline\n"
        f"  attempts:      {len(attempts)}   answers: {len(answers)}\n\n"
        f"Log in as hr1@example.com or applicant1@example.com (password: {PASSWORD})"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="delete existing dummy data (all non-admin users + job/application/"
        "assessment rows) before seeding",
    )
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        if args.wipe:
            await wipe(db)
        elif await already_seeded(db):
            print(
                f"Looks already seeded ({SENTINEL_EMAIL} exists). "
                "Re-run with --wipe to reset."
            )
            return
        await seed(db)


if __name__ == "__main__":
    # psycopg's async driver can't run under Windows' default ProactorEventLoop.
    asyncio.run(
        main(),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )
