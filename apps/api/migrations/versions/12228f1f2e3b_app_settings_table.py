"""app settings table

Revision ID: 12228f1f2e3b
Revises: ff8881fbf66e
Create Date: 2026-11-11 02:45:14.945675

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '12228f1f2e3b'
down_revision: Union[str, Sequence[str], None] = 'ff8881fbf66e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('appsetting',
    sa.Column('key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('value', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('key')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('appsetting')
