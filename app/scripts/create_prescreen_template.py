"""One-off: create a pre-assessment template with a fixed set of screening
questions.

    uv run python -m app.scripts.create_prescreen_template
"""

import asyncio
import selectors
import uuid

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.domains.assessments.pre_assessment_templates.models import (
    PreAssessmentQuestion,
    PreAssessmentTemplate,
)

TITLE = "Pre-Screening Questionnaire"

QUESTIONS = [
    ("Are you willing to work onsite?", "boolean", None),
    ("What are your salary expectations?", "text", {"max_length": 200}),
    (
        "When can you start, and do you have any scheduling constraints?",
        "long_text",
        {"max_length": 1000},
    ),
    (
        "Why are you considering a new opportunity?",
        "long_text",
        {"max_length": 1000},
    ),
    (
        "What would make you stay with a company long term?",
        "long_text",
        {"max_length": 1000},
    ),
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(
            select(PreAssessmentTemplate).where(
                PreAssessmentTemplate.title == TITLE
            )
        )
        if existing is not None:
            print(f"Template '{TITLE}' already exists ({existing.id}) — skipping.")
            return

        template = PreAssessmentTemplate(
            id=uuid.uuid4(),
            title=TITLE,
            description="Baseline screening: logistics, motivation, retention.",
            instructions="Please answer every question honestly.",
            time_limit_minutes=20,
        )
        db.add(template)
        await db.flush()  # questions FK the template; no ORM relationship to order it
        for i, (prompt, qtype, config) in enumerate(QUESTIONS):
            db.add(
                PreAssessmentQuestion(
                    id=uuid.uuid4(),
                    template_id=template.id,
                    order_index=i,
                    prompt=prompt,
                    question_type=qtype,
                    config=config,
                    time_limit_seconds=None,
                )
            )
        await db.commit()
        print(f"Created '{TITLE}' ({template.id}) with {len(QUESTIONS)} questions.")


if __name__ == "__main__":
    asyncio.run(
        main(),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )
