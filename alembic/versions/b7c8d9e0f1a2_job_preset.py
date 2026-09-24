"""export: jobs.preset (the preset picked in the UI used to be dropped)

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("preset", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "preset")
