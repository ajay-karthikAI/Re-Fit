"""add source boards table

Revision ID: b1a2c3d4e5f6
Revises: ae5e70a110f5
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "ae5e70a110f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_boards",
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "source",
            sa.Enum("greenhouse", "lever", "rss", name="source_kind"),
            nullable=False,
        ),
        sa.Column("identifier", sa.String(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column(
            "health",
            sa.Enum("healthy", "degraded", "dead", name="board_health"),
            server_default="healthy",
            nullable=False,
        ),
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_source_boards_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_boards")),
    )
    op.create_index(op.f("ix_source_boards_user_id"), "source_boards", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_source_boards_user_id"), table_name="source_boards")
    op.drop_table("source_boards")
    sa.Enum(name="board_health").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="source_kind").drop(op.get_bind(), checkfirst=True)
