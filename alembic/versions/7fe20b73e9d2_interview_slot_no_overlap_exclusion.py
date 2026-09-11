"""interview slot no-overlap exclusion constraint (review F03)

Adds `interview_slots.ends_at` (denormalized from the parent request's
duration, kept in sync by the service on any duration edit), a generated
`during` tstzrange column, and a Postgres EXCLUDE constraint that makes two
confirmed (selected) interview slots overlapping in time impossible at the
database level — not just via the Python-side `_overlaps_confirmed` check,
which has a check-then-act race window between two concurrent requests.

Revision ID: 7fe20b73e9d2
Revises: 9ed2874b2593
Create Date: 2026-09-11
"""

import sqlalchemy as sa

from alembic import op

revision = "7fe20b73e9d2"
down_revision = "9ed2874b2593"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_slots",
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill from the parent request's duration_minutes.
    op.execute(
        """
        UPDATE interview_slots s
        SET ends_at = s.starts_at + (r.duration_minutes || ' minutes')::interval
        FROM interview_requests r
        WHERE r.id = s.request_id
        """
    )
    op.alter_column("interview_slots", "ends_at", nullable=False)

    op.execute(
        "ALTER TABLE interview_slots "
        "ADD COLUMN during tstzrange "
        "GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED"
    )
    op.execute(
        "ALTER TABLE interview_slots "
        "ADD CONSTRAINT ex_interview_slots_no_overlap "
        "EXCLUDE USING gist (during WITH &&) "
        "WHERE (selected_at IS NOT NULL)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE interview_slots DROP CONSTRAINT ex_interview_slots_no_overlap"
    )
    op.execute("ALTER TABLE interview_slots DROP COLUMN during")
    op.drop_column("interview_slots", "ends_at")
