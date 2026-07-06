"""enable pgvector extension

Revision ID: fc927ce5f97a
Revises: 4f6de2cfcf67
Create Date: 2026-07-05 10:38:46.314478

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fc927ce5f97a"
down_revision: Union[str, Sequence[str], None] = "4f6de2cfcf67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
