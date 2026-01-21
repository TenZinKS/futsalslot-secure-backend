"""add user profile fields

Revision ID: bc3d4e5f6a7b
Revises: aa1c2f3b4d5e
Create Date: 2026-01-21 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bc3d4e5f6a7b'
down_revision = 'aa1c2f3b4d5e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('full_name', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('phone_number', sa.String(length=30), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('phone_number')
        batch_op.drop_column('full_name')
