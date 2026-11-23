"""Add clients, facilities, onboarding cases, stored documents, monitoring submissions, model
spend and hand-off work items for deals created in the workbench.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NOW = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "deal_client",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("short_name", sa.String(40), nullable=False),
        sa.Column("contact_name", sa.String(80), nullable=False, server_default=""),
        sa.Column("ai_permitted", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("approval_levels", sa.Integer, nullable=False, server_default="2"),
        sa.Column("master_field_overrides", JSONB, nullable=False, server_default="{}"),
        sa.Column("audit_id", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "deal_facility",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("deal_client.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("deal_type", sa.String(40), nullable=False),
        sa.Column("commitment_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("case_id", sa.Integer),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("audit_id", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("live_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "deal_case",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("deal_client.id"), nullable=False),
        sa.Column("facility_id", sa.Integer, sa.ForeignKey("deal_facility.id")),
        sa.Column("facility_name", sa.String(120), nullable=False),
        sa.Column("deal_type", sa.String(40), nullable=False),
        sa.Column("commitment_cents", sa.BigInteger, nullable=False),
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column("state", JSONB, nullable=False, server_default="{}"),
        sa.Column("audit_id", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "deal_submission",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("facility_id", sa.Integer, sa.ForeignKey("deal_facility.id"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("state", JSONB, nullable=False, server_default="{}"),
        sa.Column("audit_id", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.UniqueConstraint("facility_id", "period"),
    )
    op.create_table(
        "deal_document",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("deal_case.id"), index=True),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("deal_submission.id"), index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("kind_source", sa.String(12), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("effective_date", sa.Date),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("content", sa.LargeBinary, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("replaces_id", sa.Integer),
        sa.Column("uploaded_by", sa.String(80), nullable=False, server_default=""),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )
    op.create_table(
        "deal_client_mapping",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("deal_client.id"), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("headers", JSONB, nullable=False),
        sa.Column("columns", JSONB, nullable=False),
        sa.Column("status_map", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.UniqueConstraint("client_id", "signature"),
    )
    op.create_table(
        "deal_llm_spend",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("day", sa.Date, nullable=False, index=True),
        sa.Column("case_id", sa.Integer, index=True),
        sa.Column("submission_id", sa.Integer, index=True),
        sa.Column("task", sa.String(40), nullable=False),
        sa.Column("model", sa.String(40), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cache_read_tokens", sa.Integer, nullable=False),
        sa.Column("cache_write_tokens", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("replay", sa.Boolean, nullable=False),
        sa.Column("seconds", sa.Numeric(8, 1), nullable=False),
    )
    op.create_table(
        "work_item",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(160), nullable=False, unique=True),
        sa.Column("subject", sa.String(80), nullable=False, index=True),
        sa.Column("chain", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("detail", sa.String(400), nullable=False, server_default=""),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("assignee", sa.String(40)),
        sa.Column("client_key", sa.String(40)),
        sa.Column("from_persona", sa.String(40)),
        sa.Column("link", sa.String(200), nullable=False, server_default=""),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("sla_hours", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True)),
        sa.Column("done_by", sa.String(40)),
        sa.Column("note", sa.String(1000)),
    )


def downgrade() -> None:
    for name in ("work_item", "deal_llm_spend", "deal_client_mapping", "deal_document",
                 "deal_submission", "deal_case", "deal_facility", "deal_client"):
        op.drop_table(name)
