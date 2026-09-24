"""drop unused frame_embeddings/transcripts tables and the vector extension

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS frame_embeddings")
    op.execute("DROP TABLE IF EXISTS transcripts")
    op.execute("DROP EXTENSION IF EXISTS vector")


def downgrade() -> None:
    pass
