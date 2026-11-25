"""analytics: demo source tags, correlation statistics, briefing cache

Revision ID: ace316c14d67
Revises: 12228f1f2e3b
Create Date: 2026-11-11 02:53:03.045356

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'ace316c14d67'
down_revision: Union[str, Sequence[str], None] = '12228f1f2e3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('briefingcache',
    sa.Column('briefing_date', sa.Date(), nullable=False),
    sa.Column('bullets', sa.JSON(), nullable=True),
    sa.Column('generated_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('briefing_date')
    )
    op.add_column('cnstest', sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='manual'))
    op.add_column('correlationcache', sa.Column('p_value', sa.Float(), nullable=False, server_default='1'))
    op.add_column('correlationcache', sa.Column('spearman_score', sa.Float(), nullable=False, server_default='0'))
    op.add_column('correlationcache', sa.Column('spearman_p', sa.Float(), nullable=False, server_default='1'))
    op.add_column('correlationcache', sa.Column('n_days', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('environmentallog', sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='manual'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('environmentallog', 'source')
    op.drop_column('correlationcache', 'n_days')
    op.drop_column('correlationcache', 'spearman_p')
    op.drop_column('correlationcache', 'spearman_score')
    op.drop_column('correlationcache', 'p_value')
    op.drop_column('cnstest', 'source')
    op.drop_table('briefingcache')
