"""imaging study hash and series info

Revision ID: ff8881fbf66e
Revises: 8eb3b474f033
Create Date: 2026-11-11 02:36:04.532039

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'ff8881fbf66e'
down_revision: Union[str, Sequence[str], None] = '8eb3b474f033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('imagingstudy', sa.Column('file_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('imagingstudy', sa.Column('series_description', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
    op.add_column('imagingstudy', sa.Column('slice_count', sa.Integer(), nullable=False, server_default='0'))
    op.create_index(op.f('ix_imagingstudy_file_hash'), 'imagingstudy', ['file_hash'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_imagingstudy_file_hash'), table_name='imagingstudy')
    op.drop_column('imagingstudy', 'slice_count')
    op.drop_column('imagingstudy', 'series_description')
    op.drop_column('imagingstudy', 'file_hash')
