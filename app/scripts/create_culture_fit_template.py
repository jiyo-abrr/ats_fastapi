"""One-off: create a culture-fit template with a fixed set of questions.

uv run python -m app.scripts.create_culture_fit_template
"""

import asyncio
import selectors
import uuid

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.domains.assessments.culture_fit_templates.models import (
    CultureFitQuestion,
    CultureFitTemplate,
)

TITLE = "Culture & Values Check"

QUESTIONS = [
    (
        "I'd rather ship something good this week than something perfect next month.",
        "rating",
        {"min": 1, "max": 5},
        120,
    ),
    (
        "How do you prefer to handle a disagreement with a teammate?",
        "single_choice",
        {
            "options": [
                "Raise it directly with them first",
                "Bring it to the team",
                "Escalate to a lead",
                "Let it go unless it keeps happening",
            ]
        },
        120,
    ),
    (
        "What kind of team culture helps you do your best work, and what drains you?",
        "long_text",
        {"max_length": 1000},
        None,
    ),
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(
            select(CultureFitTemplate).where(CultureFitTemplate.title == TITLE)
        )
        if existing is not None:
            print(f"Template '{TITLE}' already exists ({existing.id}) — skipping.")
            return

        template = CultureFitTemplate(
            id=uuid.uuid4(),
            title=TITLE,
            description="Values and working-style alignment.",
            instructions="Go with your first instinct — there are no wrong answers.",
            time_limit_minutes=15,
        )
        db.add(template)
        await db.flush()  # questions FK the template; no ORM relationship to order it
        for i, (prompt, qtype, config, limit) in enumerate(QUESTIONS):
            db.add(
                CultureFitQuestion(
                    id=uuid.uuid4(),
                    template_id=template.id,
                    order_index=i,
                    prompt=prompt,
                    question_type=qtype,
                    config=config,
                    time_limit_seconds=limit,
                )
            )
        await db.commit()
        print(f"Created '{TITLE}' ({template.id}) with {len(QUESTIONS)} questions.")


if __name__ == "__main__":
    asyncio.run(
        main(),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )
