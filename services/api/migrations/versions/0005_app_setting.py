"""Add app_setting, for run-time settings such as the AI provider key (encrypted at rest).

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_setting",
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("provider", sa.String(16), nullable=False, server_default="anthropic"),
        sa.Column("key_encrypted", sa.LargeBinary),
        sa.Column("last4", sa.String(4)),
        sa.Column("model", sa.String(80)),
        sa.Column("last_test", JSONB),
        sa.Column("updated_by", sa.String(80)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("app_setting")
