"""add resume template settings

Revision ID: c58bcb6a9c2d
Revises: 9bdf8db92f2d
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c58bcb6a9c2d"
down_revision: Union[str, Sequence[str], None] = "9bdf8db92f2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resume_versions",
        sa.Column(
            "template_id",
            sa.String(),
            server_default="classic",
            nullable=False,
        ),
    )
    op.add_column(
        "resume_versions",
        sa.Column(
            "template_variables",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("resume_versions", "template_variables")
    op.drop_column("resume_versions", "template_id")
