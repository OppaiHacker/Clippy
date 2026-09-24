"""clip trash: clips.deleted_at

Revision ID: a1b2c3d4e5f6
Revises: 7078b7e3e3df
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "7078b7e3e3df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clips", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_clips_deleted_at", "clips", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_clips_deleted_at", table_name="clips")
    op.drop_column("clips", "deleted_at")
