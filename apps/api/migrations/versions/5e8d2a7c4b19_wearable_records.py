"""wearable_records

Revision ID: 5e8d2a7c4b19
Revises: 721ce95ff037
Create Date: 2026-11-16 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '5e8d2a7c4b19'
down_revision: Union[str, Sequence[str], None] = '721ce95ff037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('wearablerecord',
    sa.Column('key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('field', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('origin', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_index(op.f('ix_wearablerecord_day'), 'wearablerecord', ['day'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_wearablerecord_day'), table_name='wearablerecord')
    op.drop_table('wearablerecord')
