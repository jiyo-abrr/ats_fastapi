"""add published_at, closed_at, expires_at to job_posts

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_posts",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "job_posts",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "job_posts",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill existing posts so the recruitment report has a sensible
    # published_at/closed_at for data created before this column existed,
    # instead of leaving every historical post NULL.
    op.execute(
        "UPDATE job_posts SET published_at = created_at "
        "WHERE status IN ('published', 'closed') AND published_at IS NULL"
    )
    op.execute(
        "UPDATE job_posts SET closed_at = updated_at "
        "WHERE status = 'closed' AND closed_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("job_posts", "expires_at")
    op.drop_column("job_posts", "closed_at")
    op.drop_column("job_posts", "published_at")
