"""Frozen initial infrastructure schema. Do not import mutable runtime metadata here."""

from alembic import op
import sqlalchemy as sa

revision = "m02_2_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "platform_outbox",
        sa.Column("producer", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("aggregate_version", sa.Integer, nullable=False),
        sa.Column("occurred_at", sa.DateTime, nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("causation_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("available_at", sa.DateTime, nullable=False),
        sa.Column("lease_token", sa.String(32)),
        sa.Column("lease_until", sa.DateTime),
        sa.Column("published_at", sa.DateTime),
        sa.Column("last_error_code", sa.String(64)),
        sa.CheckConstraint(
            "status IN ('PENDING','LEASED','PUBLISHED','DEAD')", name="ck_outbox_status"
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND schema_version > 0 AND aggregate_version > 0",
            name="ck_outbox_versions",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
    )
    op.create_index("ix_outbox_due", "platform_outbox", ["producer", "status", "available_at"])
    op.create_table(
        "platform_inbox",
        sa.Column("consumer", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("result_ref", sa.String(128), nullable=False),
        sa.Column("processed_at", sa.DateTime, nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
    )


def downgrade():
    # Fail closed if any recoverable history exists. Real development data is never auto-dropped.
    for name in ("platform_outbox", "platform_inbox"):
        table = sa.table(name)
        if op.get_bind().scalar(sa.select(sa.func.count()).select_from(table)):
            raise RuntimeError("Refusing downgrade of non-empty event history")
    op.drop_table("platform_inbox")
    op.drop_table("platform_outbox")
