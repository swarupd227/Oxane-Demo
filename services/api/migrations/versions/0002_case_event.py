"""Add the append-only case event log.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("onboarding_case", sa.Column("session_id", sa.String(32), nullable=True))
    op.create_table(
        "case_event",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(32), nullable=False, index=True),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(32), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("earlier", sa.Boolean, nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("session_id", "seq"),
    )
    # The rule lives in the database, so no code path can quietly rewrite history.
    op.execute("""
        CREATE FUNCTION refuse_case_event_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'case_event is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER case_event_append_only
        BEFORE UPDATE OR DELETE ON case_event
        FOR EACH ROW EXECUTE FUNCTION refuse_case_event_change()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER case_event_append_only ON case_event")
    op.execute("DROP FUNCTION refuse_case_event_change")
    op.drop_table("case_event")
    op.drop_column("onboarding_case", "session_id")
