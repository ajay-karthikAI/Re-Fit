"""add phase 2 prose artifacts

Revision ID: 9bdf8db92f2d
Revises: 71f1f6f1d3d4
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9bdf8db92f2d"
down_revision: Union[str, Sequence[str], None] = "71f1f6f1d3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cover_letter_tone = postgresql.ENUM(
        "standard",
        "direct",
        "warm",
        name="cover_letter_tone",
        create_type=False,
    )
    followup_kind = postgresql.ENUM(
        "post_apply",
        "post_interview",
        "checkin",
        name="followup_kind",
        create_type=False,
    )
    cover_letter_tone.create(op.get_bind(), checkfirst=True)
    followup_kind.create(op.get_bind(), checkfirst=True)
    op.execute("ALTER TYPE document_kind ADD VALUE IF NOT EXISTS 'cover_letter_docx'")

    op.create_table(
        "cover_letters",
        sa.Column("job_target_id", sa.Uuid(), nullable=False),
        sa.Column("resume_version_id", sa.Uuid(), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("tone", cover_letter_tone, nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
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
            name=op.f("fk_cover_letters_job_target_id_job_targets"),
        ),
        sa.ForeignKeyConstraint(
            ["resume_version_id"],
            ["resume_versions.id"],
            name=op.f("fk_cover_letters_resume_version_id_resume_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cover_letters")),
        sa.UniqueConstraint(
            "job_target_id",
            "resume_version_id",
            "tone",
            name=op.f("uq_cover_letters_job_target_id_resume_version_id_tone"),
        ),
    )
    op.create_index(op.f("ix_cover_letters_job_target_id"), "cover_letters", ["job_target_id"])
    op.create_index(
        op.f("ix_cover_letters_resume_version_id"), "cover_letters", ["resume_version_id"]
    )

    op.create_table(
        "followups",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("kind", followup_kind, nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("send_after", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_followups_application_id_applications"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_followups")),
    )
    op.create_index(op.f("ix_followups_application_id"), "followups", ["application_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_followups_application_id"), table_name="followups")
    op.drop_table("followups")
    op.drop_index(op.f("ix_cover_letters_resume_version_id"), table_name="cover_letters")
    op.drop_index(op.f("ix_cover_letters_job_target_id"), table_name="cover_letters")
    op.drop_table("cover_letters")
    sa.Enum(name="followup_kind").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="cover_letter_tone").drop(op.get_bind(), checkfirst=True)

    op.execute(
        "UPDATE documents SET kind = 'cover_letter_pdf' WHERE kind::text = 'cover_letter_docx'"
    )
    op.execute("ALTER TYPE document_kind RENAME TO document_kind_old")
    document_kind = postgresql.ENUM(
        "resume_pdf",
        "resume_docx",
        "cover_letter_pdf",
        name="document_kind",
        create_type=False,
    )
    document_kind.create(op.get_bind(), checkfirst=True)
    op.execute(
        "ALTER TABLE documents ALTER COLUMN kind TYPE document_kind USING kind::text::document_kind"
    )
    op.execute("DROP TYPE document_kind_old")
