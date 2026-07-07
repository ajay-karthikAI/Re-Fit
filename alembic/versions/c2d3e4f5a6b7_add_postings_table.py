"""add postings table

Revision ID: c2d3e4f5a6b7
Revises: b1a2c3d4e5f6
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1a2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "postings",
        sa.Column("source_board_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description_text", sa.Text(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canonical_posting_id", sa.Uuid(), nullable=True),
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
            ["source_board_id"],
            ["source_boards.id"],
            name=op.f("fk_postings_source_board_id_source_boards"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_posting_id"],
            ["postings.id"],
            name=op.f("fk_postings_canonical_posting_id_postings"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_postings")),
        sa.UniqueConstraint("source_board_id", "external_id", name="uq_postings_board_external_id"),
    )
    op.create_index(op.f("ix_postings_source_board_id"), "postings", ["source_board_id"])
    op.create_index(op.f("ix_postings_last_seen_at"), "postings", ["last_seen_at"])
    op.create_index(op.f("ix_postings_is_active"), "postings", ["is_active"])
    op.create_index(op.f("ix_postings_canonical_posting_id"), "postings", ["canonical_posting_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_postings_canonical_posting_id"), table_name="postings")
    op.drop_index(op.f("ix_postings_is_active"), table_name="postings")
    op.drop_index(op.f("ix_postings_last_seen_at"), table_name="postings")
    op.drop_index(op.f("ix_postings_source_board_id"), table_name="postings")
    op.drop_table("postings")
