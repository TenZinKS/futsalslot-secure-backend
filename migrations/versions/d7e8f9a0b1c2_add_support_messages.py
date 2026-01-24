"""add support messages

Revision ID: d7e8f9a0b1c2
Revises: c9d1e2f3a4b5
Create Date: 2026-01-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7e8f9a0b1c2'
down_revision = 'c9d1e2f3a4b5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'support_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('court_id', sa.Integer(), nullable=True),
        sa.Column('subject', sa.String(length=160), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['court_id'], ['courts.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('support_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_support_messages_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_messages_court_id'), ['court_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_messages_status'), ['status'], unique=False)


def downgrade():
    with op.batch_alter_table('support_messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_support_messages_status'))
        batch_op.drop_index(batch_op.f('ix_support_messages_court_id'))
        batch_op.drop_index(batch_op.f('ix_support_messages_user_id'))

    op.drop_table('support_messages')
