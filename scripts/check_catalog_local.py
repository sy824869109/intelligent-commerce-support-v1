"""M04.2 本机迁移验收；可显式升级，不导入商品、不接受任意数据库地址。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/persistence"))


def verify(upgrade=False):
    """复用 M01 所有权检查；检查商品模型、读权限与迁移版本。"""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import func, inspect, select, text
    from database_local import load_database
    from ics_persistence.commerce_schema import TABLES
    from ics_persistence.migration import migrate
    from ics_persistence.schema import metadata
    from ics_persistence.identity_schema import role_permissions
    from ics_persistence.version import HEAD

    database = load_database()
    try:
        with database.engine.connect() as connection:
            before = connection.scalar(text("SELECT version_num FROM platform_alembic_version"))
        if before not in {"m03_0003", "m04_0004", HEAD}:
            raise ValueError("Unexpected pre-M04 revision")
        if upgrade:
            migrate(database.engine)
        if not database.ready():
            raise ValueError("Explicit schema upgrade required")
        with database.engine.connect() as connection:
            names = set(inspect(connection).get_table_names())
            expected = {table.name for table in TABLES}
            if not expected <= names:
                raise ValueError("Catalog tables missing")
            # M01 哨兵等既有非本模块表不纳入迁移差异判断。
            context = MigrationContext.configure(
                connection,
                opts={
                    "include_object": lambda obj, name, kind, reflected, compare_to: (
                        kind != "table" or name in metadata.tables
                    ),
                },
            )
            if compare_metadata(context, metadata):
                raise ValueError("Runtime metadata differs from database")
            counts = {
                table.name: connection.scalar(select(func.count()).select_from(table))
                for table in TABLES
            }
            grants = sorted(
                connection.scalars(
                    select(role_permissions.c.role_id).where(
                        role_permissions.c.permission_id == "product.read"
                    )
                ).all()
            )
            if grants != ["ADMIN", "AGENT", "CUSTOMER"]:
                raise ValueError("Catalog read grants differ from migration")
        return {
            "before_revision": before,
            "after_revision": HEAD,
            "tables": counts,
            "schema_matches": True,
            "catalog_rows_written_by_probe": 0,
            "new_tables_empty": all(count == 0 for count in counts.values()),
            "product_read_roles": grants,
        }
    finally:
        database.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upgrade", action="store_true", help="Apply the reviewed additive migration"
    )
    args = parser.parse_args()
    result = {"checked_at": datetime.now(timezone.utc).isoformat()}
    try:
        result.update(status="PASS", details=verify(args.upgrade))
    except Exception as exc:
        result.update(status="FAILED", error_type=type(exc).__name__)
    folder = ROOT / "_local_artifacts/m04-2"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("local-upgrade.json" if args.upgrade else "local-schema.json")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
