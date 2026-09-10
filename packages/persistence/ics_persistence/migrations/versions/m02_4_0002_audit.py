"""Add audit records; preserve all pre-existing event tables and records."""

from alembic import op
import sqlalchemy as sa

revision = "m02_4_0002"
down_revision = "m02_2_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "platform_audit",
        sa.Column("tenant_ref", sa.String(64), primary_key=True),
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("record_json", sa.Text, nullable=False),
        sa.Column("record_hash", sa.String(64), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
    )


def downgrade():
    # Preflight all history before any MySQL DDL (which implicitly commits).
    for name in ("platform_audit", "platform_outbox", "platform_inbox"):
        if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(name))):
            raise RuntimeError("Refusing downgrade of non-empty platform history")
    op.drop_table("platform_audit")
