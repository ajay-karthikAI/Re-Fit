"""add source_ats to job_targets

Revision ID: ae5e70a110f5
Revises: 53c73eff897d
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ae5e70a110f5"
down_revision: Union[str, Sequence[str], None] = "53c73eff897d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows predate ATS detection; server_default backfills them as
    # 'unknown'. New rows get a concrete value from detect_ats at creation time.
    op.add_column(
        "job_targets",
        sa.Column("source_ats", sa.String(), server_default="unknown", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("job_targets", "source_ats")
