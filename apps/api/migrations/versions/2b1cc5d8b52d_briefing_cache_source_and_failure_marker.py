"""briefing cache source and failure marker

Revision ID: 2b1cc5d8b52d
Revises: ace316c14d67
Create Date: 2026-11-11 03:16:52.771795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '2b1cc5d8b52d'
down_revision: Union[str, Sequence[str], None] = 'ace316c14d67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('briefingcache', sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='real'))
    op.add_column('briefingcache', sa.Column('failed', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('briefingcache', 'failed')
    op.drop_column('briefingcache', 'source')
