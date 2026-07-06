"""add pipeline runs table

Revision ID: 71f1f6f1d3d4
Revises: 0edc54022e3a
Create Date: 2026-07-05 21:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "71f1f6f1d3d4"
down_revision: Union[str, Sequence[str], None] = "0edc54022e3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    status = postgresql.ENUM(
        "pending",
        "running",
        "succeeded",
        "failed",
        name="pipeline_run_status",
        create_type=False,
    )
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "pipeline_runs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("job_target_id", sa.Uuid(), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("timings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_target_id"],
            ["job_targets.id"],
            name=op.f("fk_pipeline_runs_job_target_id_job_targets"),
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["uploads.id"],
            name=op.f("fk_pipeline_runs_upload_id_uploads"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_pipeline_runs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_runs")),
    )
    op.create_index(op.f("ix_pipeline_runs_job_target_id"), "pipeline_runs", ["job_target_id"])
    op.create_index(op.f("ix_pipeline_runs_upload_id"), "pipeline_runs", ["upload_id"])
    op.create_index(op.f("ix_pipeline_runs_user_id"), "pipeline_runs", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_pipeline_runs_user_id"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_upload_id"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_job_target_id"), table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
    sa.Enum(name="pipeline_run_status").drop(op.get_bind(), checkfirst=True)
