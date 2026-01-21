"""add password history and expiry tracking

Revision ID: aa1c2f3b4d5e
Revises: f786bf8df422
Create Date: 2026-01-20 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aa1c2f3b4d5e'
down_revision = 'f786bf8df422'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('password_changed_at', sa.DateTime(), server_default=sa.func.now(), nullable=False))

    op.create_table(
        'password_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('password_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_password_history_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('password_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_password_history_user_id'))

    op.drop_table('password_history')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('password_changed_at')
