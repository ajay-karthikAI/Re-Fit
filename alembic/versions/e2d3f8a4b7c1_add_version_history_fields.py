"""add version history fields

Revision ID: e2d3f8a4b7c1
Revises: c58bcb6a9c2d
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e2d3f8a4b7c1"
down_revision: Union[str, Sequence[str], None] = "c58bcb6a9c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_resume_versions_profile_job_target", table_name="resume_versions")
    op.add_column(
        "resume_versions",
        sa.Column("score_cache", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "resume_versions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_resume_versions_deleted_at"),
        "resume_versions",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        "uq_resume_versions_profile_job_target",
        "resume_versions",
        ["profile_id", "job_target_id"],
        unique=True,
        postgresql_where=sa.text("job_target_id IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_resume_versions_profile_job_target", table_name="resume_versions")
    op.drop_index(op.f("ix_resume_versions_deleted_at"), table_name="resume_versions")
    op.drop_column("resume_versions", "deleted_at")
    op.drop_column("resume_versions", "score_cache")
    op.create_index(
        "uq_resume_versions_profile_job_target",
        "resume_versions",
        ["profile_id", "job_target_id"],
        unique=True,
        postgresql_where=sa.text("job_target_id IS NOT NULL"),
    )
