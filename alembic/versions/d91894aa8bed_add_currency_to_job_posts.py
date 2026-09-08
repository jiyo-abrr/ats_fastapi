"""add currency to job_posts

Revision ID: d91894aa8bed
Revises: bb2229b90efd
Create Date: 2026-09-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from app.domains.job_posts.enums import Currency

revision: str = "d91894aa8bed"
down_revision: Union[str, Sequence[str], None] = "bb2229b90efd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALLOWED = ", ".join(f"'{c.value}'" for c in Currency)


def upgrade() -> None:
    op.add_column(
        "job_posts",
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="PHP",
        ),
    )
    op.create_check_constraint(
        "ck_job_posts_currency",
        "job_posts",
        f"currency IN ({_ALLOWED})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_job_posts_currency", "job_posts", type_="check")
    op.drop_column("job_posts", "currency")
