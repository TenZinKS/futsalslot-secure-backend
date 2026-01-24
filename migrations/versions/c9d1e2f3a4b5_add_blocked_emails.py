"""add blocked emails

Revision ID: c9d1e2f3a4b5
Revises: b1c2d3e4f5a6
Create Date: 2026-01-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d1e2f3a4b5'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'blocked_emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('email_normalized', sa.String(length=255), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('blocked_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['blocked_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email_normalized')
    )
    with op.batch_alter_table('blocked_emails', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_blocked_emails_email_normalized'), ['email_normalized'], unique=True)


def downgrade():
    with op.batch_alter_table('blocked_emails', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_blocked_emails_email_normalized'))

    op.drop_table('blocked_emails')
