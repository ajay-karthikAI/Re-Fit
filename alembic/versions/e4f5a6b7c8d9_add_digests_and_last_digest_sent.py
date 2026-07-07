"""add digests table and saved_search.last_digest_sent_at

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "saved_searches",
        sa.Column("last_digest_sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "digests",
        sa.Column("saved_search_id", sa.Uuid(), nullable=False),
        sa.Column("new_match_count", sa.Integer(), nullable=False),
        sa.Column("posting_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["saved_search_id"],
            ["saved_searches.id"],
            name=op.f("fk_digests_saved_search_id_saved_searches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_digests")),
    )
    op.create_index(op.f("ix_digests_saved_search_id"), "digests", ["saved_search_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_digests_saved_search_id"), table_name="digests")
    op.drop_table("digests")
    op.drop_column("saved_searches", "last_digest_sent_at")
