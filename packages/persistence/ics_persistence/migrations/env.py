"""Only explicitly supplied connections; no auto-created engine or automatic .env load."""

from alembic import context

connection = context.config.attributes.get("connection")
if connection is None or context.is_offline_mode():
    raise RuntimeError("A reviewed online connection is required")
context.configure(
    connection=connection,
    version_table="platform_alembic_version",
    transactional_ddl=False,
)
with context.begin_transaction():
    context.run_migrations()
