"""add answer profile and short answers

Revision ID: 53c73eff897d
Revises: e2d3f8a4b7c1
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "53c73eff897d"
down_revision: Union[str, Sequence[str], None] = "e2d3f8a4b7c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "answer_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "work_auth",
            sa.Enum(
                "citizen",
                "permanent_resident",
                "visa_holder",
                "needs_sponsorship",
                "other",
                name="work_auth_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "sponsorship_needed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("salary_type", sa.Enum("annual", "hourly", name="salary_type"), nullable=False),
        sa.Column(
            "relocation",
            sa.Enum("yes", "no", "case_by_case", name="relocation_preference"),
            nullable=False,
        ),
        sa.Column("notice_period_days", sa.Integer(), nullable=True),
        sa.Column("pronouns", sa.String(), nullable=True),
        sa.Column("referral_source_default", sa.String(), nullable=True),
        sa.Column("eeo_prefs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_answer_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_profiles")),
    )
    op.create_index(op.f("ix_answer_profiles_user_id"), "answer_profiles", ["user_id"], unique=True)

    op.create_table(
        "short_answers",
        sa.Column("job_target_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_hash", sa.String(length=64), nullable=False),
        sa.Column("answer_markdown", sa.Text(), nullable=False),
        sa.Column(
            "question_kind",
            sa.Enum("why_company", "why_role", "custom", name="short_answer_kind"),
            nullable=False,
        ),
        sa.Column("claim_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_target_id"],
            ["job_targets.id"],
            name=op.f("fk_short_answers_job_target_id_job_targets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_short_answers")),
        sa.UniqueConstraint(
            "job_target_id",
            "question_hash",
            name=op.f("uq_short_answers_job_target_id_question_hash"),
        ),
    )
    op.create_index(op.f("ix_short_answers_job_target_id"), "short_answers", ["job_target_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_short_answers_job_target_id"), table_name="short_answers")
    op.drop_table("short_answers")
    sa.Enum(name="short_answer_kind").drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f("ix_answer_profiles_user_id"), table_name="answer_profiles")
    op.drop_table("answer_profiles")
    sa.Enum(name="relocation_preference").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="salary_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="work_auth_status").drop(op.get_bind(), checkfirst=True)
