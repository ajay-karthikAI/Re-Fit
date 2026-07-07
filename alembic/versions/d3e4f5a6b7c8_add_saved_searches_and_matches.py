"""add saved searches, posting matches, and posting requirements cache

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "postings",
        sa.Column("extracted_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "saved_searches",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("min_score", sa.Float(), server_default=sa.text("75.0"), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            name=op.f("fk_saved_searches_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_saved_searches_profile_id_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_searches")),
    )
    op.create_index(op.f("ix_saved_searches_user_id"), "saved_searches", ["user_id"])
    op.create_index(op.f("ix_saved_searches_is_active"), "saved_searches", ["is_active"])

    op.create_table(
        "posting_matches",
        sa.Column("posting_id", sa.Uuid(), nullable=False),
        sa.Column("saved_search_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("missing_terms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("scored_content_hash", sa.Text(), nullable=False),
        sa.Column("scored_profile_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["posting_id"],
            ["postings.id"],
            name=op.f("fk_posting_matches_posting_id_postings"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["saved_search_id"],
            ["saved_searches.id"],
            name=op.f("fk_posting_matches_saved_search_id_saved_searches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posting_matches")),
        sa.UniqueConstraint(
            "posting_id", "saved_search_id", name="uq_posting_matches_posting_search"
        ),
    )
    op.create_index(op.f("ix_posting_matches_posting_id"), "posting_matches", ["posting_id"])
    op.create_index(
        op.f("ix_posting_matches_saved_search_id"), "posting_matches", ["saved_search_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_posting_matches_saved_search_id"), table_name="posting_matches")
    op.drop_index(op.f("ix_posting_matches_posting_id"), table_name="posting_matches")
    op.drop_table("posting_matches")
    op.drop_index(op.f("ix_saved_searches_is_active"), table_name="saved_searches")
    op.drop_index(op.f("ix_saved_searches_user_id"), table_name="saved_searches")
    op.drop_table("saved_searches")
    op.drop_column("postings", "extracted_requirements")
