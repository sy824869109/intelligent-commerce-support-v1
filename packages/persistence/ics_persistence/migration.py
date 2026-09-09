"""Programmatic Alembic entry: caller supplies a connection; never embeds a secret URL."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from .version import HEAD as HEAD


def migrate(engine, target="head", *, downgrade=False):
    if target not in {"head", "base"} or (target == "base") != downgrade:
        raise ValueError("Only reviewed upgrade head / downgrade base are supported")
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    with engine.connect() as connection:
        # DDL on MySQL implicitly commits; migration is NOT a multi-statement atomic rollback.
        config.attributes["connection"] = connection
        is_mysql = engine.dialect.name == "mysql"
        if is_mysql:
            if connection.scalar(text("SELECT GET_LOCK('ics_m02_platform_migration', 2)")) != 1:
                raise RuntimeError("Migration already running")
            connection.commit()
        try:
            tables = set(inspect(connection).get_table_names())
            if "platform_alembic_version" not in tables and tables & {
                "platform_outbox",
                "platform_inbox",
            }:
                raise RuntimeError("Unversioned infrastructure tables require manual review")
            connection.commit()
            if downgrade:
                command.downgrade(config, target)
            else:
                command.upgrade(config, target)
            connection.commit()
        finally:
            if is_mysql:
                connection.rollback()
                connection.execute(text("SELECT RELEASE_LOCK('ics_m02_platform_migration')"))
                connection.commit()
