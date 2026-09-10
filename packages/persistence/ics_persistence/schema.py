"""Only the M02 event infrastructure tables; business schemas belong to later owners."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
)

from .identity_schema import metadata

audit = Table(
    "platform_audit",
    metadata,
    Column("tenant_ref", String(64), primary_key=True),
    Column("event_id", String(64), primary_key=True),
    Column("record_json", Text, nullable=False),
    Column("record_hash", String(64), nullable=False),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_bin",
)
outbox = Table(
    "platform_outbox",
    metadata,
    Column("producer", String(64), primary_key=True),
    Column("tenant_id", String(64), primary_key=True),
    Column("event_id", String(64), primary_key=True),
    Column("event_type", String(128), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("aggregate_type", String(64), nullable=False),
    Column("aggregate_id", String(64), nullable=False),
    Column("aggregate_version", Integer, nullable=False),
    Column("occurred_at", DateTime, nullable=False),
    Column("correlation_id", String(64), nullable=False),
    Column("causation_id", String(64), nullable=False),
    Column("trace_id", String(64), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("available_at", DateTime, nullable=False),
    Column("lease_token", String(32)),
    Column("lease_until", DateTime),
    Column("published_at", DateTime),
    Column("last_error_code", String(64)),
    CheckConstraint("status IN ('PENDING','LEASED','PUBLISHED','DEAD')", name="ck_outbox_status"),
    CheckConstraint(
        "attempts >= 0 AND schema_version > 0 AND aggregate_version > 0", name="ck_outbox_versions"
    ),
    Index("ix_outbox_due", "producer", "status", "available_at"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_bin",
)
inbox = Table(
    "platform_inbox",
    metadata,
    Column("consumer", String(64), primary_key=True),
    Column("tenant_id", String(64), primary_key=True),
    Column("event_id", String(64), primary_key=True),
    Column("payload_hash", String(64), nullable=False),
    Column("result_ref", String(128), nullable=False),
    Column("processed_at", DateTime, nullable=False),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_bin",
)
