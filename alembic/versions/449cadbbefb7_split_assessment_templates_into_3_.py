"""split assessment templates into 3 independent domains

Revision ID: 449cadbbefb7
Revises: f01904f00789
Create Date: 2026-09-06 07:19:23.785892

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '449cadbbefb7'
down_revision: Union[str, Sequence[str], None] = 'f01904f00789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Dev-only: no real applicant data to preserve. Existing test rows in
    # assessment_attempts/assessment_answers reference the old single
    # assessment_templates/assessment_questions tables — clear them before
    # restructuring rather than writing a backfill (same call as the earlier
    # status-pipeline migration made for the same reason).
    op.execute("DELETE FROM assessment_attempt_reopens")
    op.execute("DELETE FROM assessment_answers")
    op.execute("DELETE FROM assessment_attempts")

    # ### new tables — one pair (template + questions) per independent domain ###
    op.create_table('pre_assessment_templates',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=True),
    sa.Column('instructions', sa.String(length=4000), nullable=True),
    sa.Column('time_limit_minutes', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('culture_fit_templates',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=True),
    sa.Column('instructions', sa.String(length=4000), nullable=True),
    sa.Column('time_limit_minutes', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('technical_assessment_templates',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=True),
    sa.Column('instructions', sa.String(length=4000), nullable=True),
    sa.Column('time_limit_minutes', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pre_assessment_questions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('template_id', sa.UUID(), nullable=False),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('prompt', sa.String(length=2000), nullable=False),
    sa.Column('instructions', sa.String(length=1000), nullable=True),
    sa.Column('question_type', sa.String(length=20), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('time_limit_seconds', sa.Integer(), nullable=True),
    sa.CheckConstraint("question_type IN ('text', 'long_text', 'single_choice', 'multiple_choice', 'boolean', 'number', 'rating', 'date')", name='ck_pre_assessment_questions_question_type'),
    sa.ForeignKeyConstraint(['template_id'], ['pre_assessment_templates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('culture_fit_questions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('template_id', sa.UUID(), nullable=False),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('prompt', sa.String(length=2000), nullable=False),
    sa.Column('instructions', sa.String(length=1000), nullable=True),
    sa.Column('question_type', sa.String(length=20), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('time_limit_seconds', sa.Integer(), nullable=True),
    sa.CheckConstraint("question_type IN ('text', 'long_text', 'single_choice', 'multiple_choice', 'boolean', 'number', 'rating', 'date')", name='ck_culture_fit_questions_question_type'),
    sa.ForeignKeyConstraint(['template_id'], ['culture_fit_templates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('technical_assessment_questions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('template_id', sa.UUID(), nullable=False),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('prompt', sa.String(length=2000), nullable=False),
    sa.Column('instructions', sa.String(length=1000), nullable=True),
    sa.Column('question_type', sa.String(length=20), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('time_limit_seconds', sa.Integer(), nullable=True),
    sa.CheckConstraint("question_type IN ('text', 'long_text', 'single_choice', 'multiple_choice', 'boolean', 'number', 'rating', 'date')", name='ck_technical_assessment_questions_question_type'),
    sa.ForeignKeyConstraint(['template_id'], ['technical_assessment_templates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('job_post_pre_assessment_templates',
    sa.Column('job_post_id', sa.UUID(), nullable=False),
    sa.Column('template_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['job_post_id'], ['job_posts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['template_id'], ['pre_assessment_templates.id'], ),
    sa.PrimaryKeyConstraint('job_post_id')
    )
    op.create_table('job_post_culture_fit_templates',
    sa.Column('job_post_id', sa.UUID(), nullable=False),
    sa.Column('template_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['job_post_id'], ['job_posts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['template_id'], ['culture_fit_templates.id'], ),
    sa.PrimaryKeyConstraint('job_post_id')
    )
    op.create_table('job_post_technical_assessment_templates',
    sa.Column('job_post_id', sa.UUID(), nullable=False),
    sa.Column('template_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['job_post_id'], ['job_posts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['template_id'], ['technical_assessment_templates.id'], ),
    sa.PrimaryKeyConstraint('job_post_id')
    )

    # ### assessment_attempts / assessment_answers: drop FKs to the old
    # tables BEFORE dropping those tables — both assessment_attempts and
    # assessment_answers survive this migration, so their own constraints
    # must go first, not as a side effect of dropping the referenced tables ###
    op.drop_constraint(op.f('assessment_attempts_template_id_fkey'), 'assessment_attempts', type_='foreignkey')
    op.drop_constraint(op.f('assessment_answers_question_id_fkey'), 'assessment_answers', type_='foreignkey')

    op.add_column('assessment_attempts', sa.Column('template_type', sa.String(length=20), nullable=False))
    op.create_check_constraint(
        'ck_assessment_attempts_template_type',
        'assessment_attempts',
        "template_type IN ('pre_assessment', 'culture_fit', 'technical')",
    )
    op.drop_constraint(op.f('ux_assessment_attempts_unique'), 'assessment_attempts', type_='unique')
    op.create_unique_constraint('ux_assessment_attempts_unique', 'assessment_attempts', ['application_id', 'template_type'])

    # ### now safe to drop the old tables — nothing references them anymore ###
    op.drop_table('job_post_assessment_templates')
    op.drop_table('assessment_questions')
    op.drop_table('assessment_templates')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('assessment_templates',
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('type', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('title', sa.VARCHAR(length=200), autoincrement=False, nullable=False),
    sa.Column('description', sa.VARCHAR(length=2000), autoincrement=False, nullable=True),
    sa.Column('instructions', sa.VARCHAR(length=4000), autoincrement=False, nullable=True),
    sa.Column('time_limit_minutes', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("type IN ('pre_assessment', 'culture_fit', 'technical')", name='ck_assessment_templates_type'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('assessment_questions',
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('template_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('order_index', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('prompt', sa.VARCHAR(length=2000), autoincrement=False, nullable=False),
    sa.Column('instructions', sa.VARCHAR(length=1000), autoincrement=False, nullable=True),
    sa.Column('question_type', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('time_limit_seconds', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.CheckConstraint("question_type IN ('text', 'long_text', 'single_choice', 'multiple_choice', 'boolean', 'number', 'rating', 'date')", name='ck_assessment_questions_question_type'),
    sa.ForeignKeyConstraint(['template_id'], ['assessment_templates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('job_post_assessment_templates',
    sa.Column('job_post_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('template_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('type', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['job_post_id'], ['job_posts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['template_id'], ['assessment_templates.id'], ),
    sa.PrimaryKeyConstraint('job_post_id', 'template_id'),
    sa.UniqueConstraint('job_post_id', 'type', name='ux_job_post_assessment_type')
    )

    op.execute("DELETE FROM assessment_attempt_reopens")
    op.execute("DELETE FROM assessment_answers")
    op.execute("DELETE FROM assessment_attempts")

    op.drop_constraint('ux_assessment_attempts_unique', 'assessment_attempts', type_='unique')
    op.create_unique_constraint(op.f('ux_assessment_attempts_unique'), 'assessment_attempts', ['application_id', 'template_id'])
    op.drop_constraint('ck_assessment_attempts_template_type', 'assessment_attempts', type_='check')
    op.drop_column('assessment_attempts', 'template_type')

    op.create_foreign_key(op.f('assessment_attempts_template_id_fkey'), 'assessment_attempts', 'assessment_templates', ['template_id'], ['id'])
    op.create_foreign_key(op.f('assessment_answers_question_id_fkey'), 'assessment_answers', 'assessment_questions', ['question_id'], ['id'])

    op.drop_table('job_post_technical_assessment_templates')
    op.drop_table('job_post_pre_assessment_templates')
    op.drop_table('job_post_culture_fit_templates')
    op.drop_table('technical_assessment_questions')
    op.drop_table('pre_assessment_questions')
    op.drop_table('culture_fit_questions')
    op.drop_table('technical_assessment_templates')
    op.drop_table('pre_assessment_templates')
    op.drop_table('culture_fit_templates')
