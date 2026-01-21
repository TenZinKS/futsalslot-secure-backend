"""add court details and images

Revision ID: c1d2e3f4a5b6
Revises: bc3d4e5f6a7b
Create Date: 2026-01-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'bc3d4e5f6a7b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('courts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('maps_link', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('courts', schema=None) as batch_op:
        batch_op.drop_column('maps_link')
        batch_op.drop_column('description')
