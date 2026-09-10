"""M03 identity metadata; domain resources remain owned by their domain services."""

from alembic import op
import sqlalchemy as sa

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
)

metadata = MetaData()

OPTIONS = dict(mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_bin")

organizations = Table(
    "identity_organizations",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(120), nullable=False),
    **OPTIONS,
)
tenants = Table(
    "identity_tenants",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("organization_id", String(64), nullable=False),
    Column("name", String(120), nullable=False),
    Column("active", Boolean, nullable=False),
    ForeignKeyConstraint(["organization_id"], ["identity_organizations.id"]),
    **OPTIONS,
)
users = Table(
    "identity_users",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("username", String(64), unique=True, nullable=False),
    Column("password_hash", String(256), nullable=False),
    Column("active", Boolean, nullable=False),
    **OPTIONS,
)
roles = Table("identity_roles", metadata, Column("id", String(32), primary_key=True), **OPTIONS)
permissions = Table(
    "identity_permissions", metadata, Column("id", String(64), primary_key=True), **OPTIONS
)
role_permissions = Table(
    "identity_role_permissions",
    metadata,
    Column("role_id", String(32), primary_key=True),
    Column("permission_id", String(64), primary_key=True),
    ForeignKeyConstraint(["role_id"], ["identity_roles.id"]),
    ForeignKeyConstraint(["permission_id"], ["identity_permissions.id"]),
    **OPTIONS,
)
memberships = Table(
    "identity_memberships",
    metadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("user_id", String(64), primary_key=True),
    Column("role_id", String(32), nullable=False),
    Column("active", Boolean, nullable=False),
    ForeignKeyConstraint(["tenant_id"], ["identity_tenants.id"]),
    ForeignKeyConstraint(["user_id"], ["identity_users.id"]),
    ForeignKeyConstraint(["role_id"], ["identity_roles.id"]),
    **OPTIONS,
)
groups = Table(
    "identity_groups",
    metadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("id", String(64), primary_key=True),
    Column("name", String(120), nullable=False),
    ForeignKeyConstraint(["tenant_id"], ["identity_tenants.id"]),
    **OPTIONS,
)
group_members = Table(
    "identity_group_members",
    metadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("group_id", String(64), primary_key=True),
    Column("user_id", String(64), primary_key=True),
    ForeignKeyConstraint(
        ["tenant_id", "group_id"], ["identity_groups.tenant_id", "identity_groups.id"]
    ),
    ForeignKeyConstraint(
        ["tenant_id", "user_id"], ["identity_memberships.tenant_id", "identity_memberships.user_id"]
    ),
    **OPTIONS,
)
sessions = Table(
    "identity_sessions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("user_id", String(64), nullable=False),
    Column("expires_at", DateTime, nullable=False),
    Column("revoked", Boolean, nullable=False),
    ForeignKeyConstraint(
        ["tenant_id", "user_id"], ["identity_memberships.tenant_id", "identity_memberships.user_id"]
    ),
    **OPTIONS,
)
tokens = Table(
    "identity_tokens",
    metadata,
    Column("digest", String(64), primary_key=True),
    Column("session_id", String(64), nullable=False, index=True),
    Column("kind", String(16), nullable=False),
    Column("expires_at", DateTime, nullable=False),
    Column("used", Boolean, nullable=False),
    ForeignKeyConstraint(["session_id"], ["identity_sessions.id"]),
    **OPTIONS,
)
login_buckets = Table(
    "identity_login_buckets",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("count", Integer, nullable=False),
    Column("expires_at", DateTime, nullable=False, index=True),
    **OPTIONS,
)

ROLE_GRANTS = {
    "CUSTOMER": ("order.read", "ticket.read", "knowledge.read"),
    "AGENT": ("order.read", "ticket.read", "ticket.reply", "knowledge.read"),
    "ADMIN": (
        "order.read",
        "ticket.read",
        "ticket.reply",
        "knowledge.read",
        "knowledge.publish",
        "identity.manage",
    ),
}

TABLES = (
    organizations,
    tenants,
    users,
    roles,
    permissions,
    role_permissions,
    memberships,
    groups,
    group_members,
    sessions,
    tokens,
    login_buckets,
)

revision = "m03_0003"
down_revision = "m02_4_0002"
branch_labels = None
depends_on = None


def upgrade():
    # Frozen metadata snapshot, never import the evolving runtime schema.
    metadata.create_all(op.get_bind(), checkfirst=False)
    op.bulk_insert(roles, [{"id": value} for value in ROLE_GRANTS])
    op.bulk_insert(
        permissions,
        [{"id": value} for value in sorted({p for ps in ROLE_GRANTS.values() for p in ps})],
    )
    op.bulk_insert(
        role_permissions,
        [{"role_id": role, "permission_id": p} for role, ps in ROLE_GRANTS.items() for p in ps],
    )


def downgrade():
    # Refuse any identity or prior platform history before the first destructive DDL.
    reference_tables = {"identity_roles", "identity_permissions", "identity_role_permissions"}
    for name in [t.name for t in TABLES if t.name not in reference_tables] + [
        "platform_audit",
        "platform_outbox",
        "platform_inbox",
    ]:
        if op.get_bind().scalar(sa.select(sa.func.count()).select_from(sa.table(name))):
            raise RuntimeError("Refusing downgrade of non-empty identity/platform history")
    metadata.drop_all(op.get_bind())
