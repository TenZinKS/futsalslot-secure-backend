"""add login_otps table

Revision ID: c3a1b2c4d5e6
Revises: f45ea82e5dad
Create Date: 2026-01-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3a1b2c4d5e6"
down_revision = "f45ea82e5dad"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_otps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("login_otps", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_login_otps_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_login_otps_token_hash"), ["token_hash"], unique=True)


def downgrade():
    with op.batch_alter_table("login_otps", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_login_otps_token_hash"))
        batch_op.drop_index(batch_op.f("ix_login_otps_user_id"))

    op.drop_table("login_otps")
