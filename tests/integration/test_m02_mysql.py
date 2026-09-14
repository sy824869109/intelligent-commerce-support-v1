"""Real MySQL-only gate. Run through check_mysql.py, never against a business database."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select, text, update
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/persistence"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/observability"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/identity"))
from ics_persistence.database import Database, DatabaseConfig
from ics_persistence.events import Event
from ics_persistence.migration import migrate
from ics_persistence.outbox import acknowledge, claim, consume, enqueue, EventConflict, retry
from ics_persistence.schema import metadata, inbox, outbox


@pytest.fixture(scope="module")
def db():
    # Missing runner configuration is a failure, not a skipped or SQLite fallback test.
    database = Database.connect(
        DatabaseConfig(
            username="ics_m02_test",
            password=os.environ["ICS_TEST_MYSQL_PASSWORD"],
            database="ics_m02_test",
            port=int(os.environ["ICS_TEST_MYSQL_PORT"]),
        )
    )
    yield database
    database.close()


def event(number=1, **overrides):
    return Event(
        **dict(
            event_id=f"EV{number}",
            producer="synthetic-producer",
            tenant_id="TENANT_A",
            event_type="synthetic.created",
            aggregate_type="synthetic",
            aggregate_id=f"A{number}",
            aggregate_version=1,
            occurred_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
            correlation_id="COR001",
            causation_id="CMD001",
            trace_id="TR001",
            payload={"ref": "中文引用"},
        )
        | overrides
    )


def put(session, item):
    return enqueue(session, item, producer=item.producer, tenant_id=item.tenant_id)


def accept(session, item, handler):
    return consume(
        session,
        item,
        consumer="synthetic-consumer",
        tenant_id="TENANT_A",
        producer="synthetic-producer",
        event_type="synthetic.created",
        schema_version=1,
        handler=handler,
    )


def test_00_m03_existing_rows_survive_catalog_upgrade(db):
    """复现真实旧库升级，不仅测试从空库直接创建最终 schema。"""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import delete, inspect
    from ics_persistence.identity_schema import organizations
    from ics_persistence.commerce_schema import TABLES

    config = Config()
    config.set_main_option(
        "script_location",
        str(
            Path(__file__).resolve().parents[2] / "packages/persistence/ics_persistence/migrations"
        ),
    )
    with db.engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "m03_0003")
        connection.commit()
    assert not db.ready()
    with db.transaction() as session:
        session.execute(insert(organizations).values(id="UPGRADE_ONLY", name="迁移前已有组织"))
    with db.engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "m04_0004")
        connection.commit()
        assert (
            connection.scalar(
                text("SELECT COUNT(*) FROM identity_permissions WHERE id = 'product.read'")
            )
            == 0
        )
    migrate(db.engine)
    assert db.ready()
    assert {table.name for table in TABLES} <= set(inspect(db.engine).get_table_names())
    with db.transaction() as session:
        assert (
            session.scalar(
                text(
                    "SELECT COUNT(*) FROM identity_role_permissions WHERE permission_id = 'product.read'"
                )
            )
            == 3
        )
        assert (
            session.scalar(select(organizations.c.name).where(organizations.c.id == "UPGRADE_ONLY"))
            == "迁移前已有组织"
        )
        # 仅删除本测试在临时库内创建的这一行，随后验证空库回退。
        session.execute(delete(organizations).where(organizations.c.id == "UPGRADE_ONLY"))
    migrate(db.engine, "base", downgrade=True)
    assert not db.ready()


def test_01_real_schema_migration_roundtrip(db):
    assert not db.ready()
    migrate(db.engine)
    assert db.ready()
    migrate(db.engine)
    with db.engine.connect() as connection:
        assert connection.scalar(text("SELECT @@transaction_isolation")) == "READ-COMMITTED"
        assert connection.scalar(text("SELECT @@session.time_zone")) == "+00:00"
        ctx = MigrationContext.configure(
            connection,
            opts={"include_object": lambda obj, name, *a: name != "platform_alembic_version"},
        )
        assert compare_metadata(ctx, metadata) == []
    migrate(db.engine, "base", downgrade=True)
    assert not db.ready()
    migrate(db.engine)
    assert db.ready()


def test_02_atomic_business_outbox_and_reopen(db):
    # Synthetic business table is confined to this runner's disposable schema.
    table = Table(
        "synthetic_effects",
        MetaData(),
        Column("id", String(64), primary_key=True),
        Column("amount", Integer),
        mysql_engine="InnoDB",
    )
    table.create(db.engine)
    with pytest.raises(RuntimeError):
        with db.transaction() as session:
            session.execute(insert(table).values(id="ROLLED_BACK", amount=1))
            put(session, event(1))
            raise RuntimeError("synthetic failure")
    with db.transaction() as session:
        assert session.execute(select(table)).first() is None
        assert session.execute(select(outbox)).first() is None
        session.execute(insert(table).values(id="COMMITTED", amount=1))
        put(session, event(2))
    db.engine.dispose()
    with db.transaction() as session:
        assert session.scalar(select(table.c.id)) == "COMMITTED"
        assert session.scalar(select(outbox.c.event_id)) == "EV2"


def test_03_concurrent_enqueue_same_id(db):
    def write(_):
        with db.transaction() as session:
            return put(session, event(3))

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(write, range(10)))
    assert results.count(True) == 1 and results.count(False) == 9
    with db.transaction() as session:
        with pytest.raises(EventConflict):
            put(session, event(3, payload={"ref": "DIFFERENT"}))


def test_04_skip_locked_and_no_uncommitted_publication(db):
    with db.transaction() as first:
        put(first, event(4))
        with db.transaction() as second:
            assert "EV4" not in [
                e.event_id for e, _ in claim(second, producer="synthetic-producer")
            ]
    with db.transaction() as first:
        [(item, token)] = claim(first, producer="synthetic-producer")
        with db.transaction() as second:
            assert claim(second, producer="synthetic-producer") == []
    assert item.event_id == "EV4"
    with db.transaction() as session:
        assert not acknowledge(session, item, "stale")
        assert acknowledge(session, item, token)


def test_05_recovery_fencing_retry_dead_and_payload_preservation(db):
    with db.transaction() as session:
        put(session, event(5))
        candidates = claim(session, producer="synthetic-producer")
        [(item, stale)] = [(e, t) for e, t in candidates if e.event_id == "EV5"]
        session.execute(
            update(outbox)
            .where(outbox.c.event_id == "EV5")
            .values(lease_until=datetime(2000, 1, 1))
        )
    with db.transaction() as session:
        [(same, token)] = claim(session, producer="synthetic-producer", max_attempts=2)
        assert same == item and stale != token
        assert not acknowledge(session, item, stale)
        assert retry(session, item, token, delay_seconds=1)
        assert not acknowledge(session, item, token)
        assert claim(session, producer="synthetic-producer") == []
        session.execute(
            update(outbox)
            .where(outbox.c.event_id == "EV5")
            .values(available_at=datetime(2000, 1, 1))
        )
    with db.transaction() as session:
        assert claim(session, producer="synthetic-producer", max_attempts=2) == []
        row = session.execute(select(outbox).where(outbox.c.event_id == "EV5")).mappings().one()
        assert row["status"] == "DEAD" and row["attempts"] == 2
        assert row["payload"] == item.payload


def test_06_inbox_concurrent_atomic_effect_and_failure(db):
    effects = Table("synthetic_effects", MetaData(), autoload_with=db.engine)

    def handler(session, item):
        # A second handler execution would violate this non-idempotent business insert.
        session.execute(insert(effects).values(id="CONSUMED_ONCE", amount=1))
        put(session, event(60))
        return "RESULT60"

    def run(_):
        with db.transaction() as session:
            return accept(session, event(6), handler)

    with ThreadPoolExecutor(max_workers=5) as pool:
        assert list(pool.map(run, range(10))) == ["RESULT60"] * 10
    with db.transaction() as session:
        assert len(session.execute(select(inbox).where(inbox.c.event_id == "EV6")).all()) == 1
        assert len(session.execute(select(outbox).where(outbox.c.event_id == "EV60")).all()) == 1

        def fail(s, e):
            put(s, event(70))
            raise RuntimeError("failure after effect")

        with pytest.raises(RuntimeError):
            accept(session, event(7), fail)
        assert session.execute(select(inbox).where(inbox.c.event_id == "EV7")).first() is None
        assert session.execute(select(outbox).where(outbox.c.event_id == "EV70")).first() is None


def test_07_tenant_case_sensitive_identity_and_scope(db):
    with db.transaction() as session:
        assert put(session, event(8, tenant_id="TENANT_A"))
        assert put(session, event(8, tenant_id="tenant_a"))
        assert put(session, event(8, tenant_id="TENANT_B"))
        with pytest.raises(ValueError):
            accept(session, event(8, tenant_id="TENANT_B"), lambda s, e: "NEVER")
        assert claim(session, producer="unknown-producer") == []


def test_08_nonempty_downgrade_fails_preserving_history(db):
    with pytest.raises(RuntimeError, match="non-empty"):
        migrate(db.engine, "base", downgrade=True)
    assert db.ready()
    with db.transaction() as session:
        assert session.execute(select(outbox)).first() is not None


def test_09_real_audit_atomic_retry_conflict_and_reconnect(db):
    from dataclasses import replace
    from ics_observability.core import AuditRecord
    from ics_observability.audit import append_audit, AuditConflict
    from ics_persistence.schema import audit

    item = AuditRecord(
        "AUD1",
        "A1",
        "TENANT_A",
        "O1",
        "R1",
        "TRACE1",
        "COMMAND_SUBMIT",
        "SUCCEEDED",
        datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    with pytest.raises(RuntimeError):
        with db.transaction() as session:
            put(session, event(91))
            append_audit(session, item, tenant_ref="TENANT_A")
            raise RuntimeError("Rollback business event and audit")
    with db.transaction() as session:
        assert session.execute(select(audit)).first() is None
        assert session.execute(select(outbox).where(outbox.c.event_id == "EV91")).first() is None
        put(session, event(92))
        assert append_audit(session, item, tenant_ref="TENANT_A")
    db.close()

    def retry_audit(_):
        with db.transaction() as session:
            return append_audit(session, item, tenant_ref="TENANT_A")

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(retry_audit, range(8))) == [False] * 8
    with pytest.raises(AuditConflict):
        with db.transaction() as session:
            put(session, event(93))
            append_audit(session, replace(item, outcome="FAILED"), tenant_ref="TENANT_A")
    with db.transaction() as session:
        assert len(session.execute(select(audit)).all()) == 1
        assert session.execute(select(outbox).where(outbox.c.event_id == "EV93")).first() is None
    with pytest.raises(RuntimeError, match="non-empty"):
        migrate(db.engine, "base", downgrade=True)
    assert db.ready()


def test_10_m03_real_session_rotation_concurrency_and_revocation(db):
    from ics_identity.passwords import hash_password
    from ics_identity.service import Identity, IdentityError, provision_tenant
    from ics_persistence.identity_schema import sessions, tokens

    password = "Synthetic-M03-Password-98!"
    with db.transaction() as session:
        provision_tenant(
            session,
            organization_id="ORG_M03",
            tenant_id="TENANT_M03",
            user_id="ADMIN_M03",
            login="admin_m03",
            password_hash=hash_password(password),
        )
    identity = Identity(db)
    pair = identity.login("TENANT_M03", "admin_m03", password, "loopback-test")
    assert identity.authenticate(pair["access_token"]).tenant_id == "TENANT_M03"
    db.close()

    def rotate(_):
        try:
            return identity.refresh(pair["refresh_token"])
        except IdentityError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(rotate, range(2)))
    assert sum(result is not None for result in results) == 1
    winner = next(result for result in results if result is not None)
    # Replayed refresh revokes even the winning successor; no double-use window persists.
    with pytest.raises(IdentityError):
        identity.authenticate(winner["access_token"])
    with db.transaction() as session:
        assert session.scalar(select(sessions.c.revoked).where(sessions.c.user_id == "ADMIN_M03"))
        assert pair["refresh_token"] not in str(session.execute(select(tokens)).all())


def test_11_m03_real_group_scope_and_role_revocation(db):
    from ics_identity.service import Identity, IdentityError, Resource

    identity = Identity(db)
    password = "Synthetic-M03-Password-98!"
    admin_pair = identity.login("TENANT_M03", "admin_m03", password, "admin-peer")
    admin = identity.authenticate(admin_pair["access_token"])
    user_id = identity.create_member(admin, "agent_m03", password, "AGENT")
    group_id = identity.create_group(admin, "synthetic-group")
    identity.group_member(admin, group_id, user_id, True)
    pair = identity.login("TENANT_M03", "agent_m03", password, "agent-peer")
    agent = identity.authenticate(pair["access_token"])
    for kind in ("order", "ticket", "knowledge"):
        with db.transaction() as session:
            identity.authorize(
                session,
                agent,
                kind + ".read",
                Resource(kind, "TENANT_M03", group_id=group_id, published=True),
            )
            with pytest.raises(IdentityError):
                identity.authorize(
                    session,
                    agent,
                    kind + ".read",
                    Resource(kind, "OTHER_TENANT", group_id=group_id, published=True),
                )
    identity.group_member(admin, group_id, user_id, False)
    with db.transaction() as session:
        with pytest.raises(IdentityError):
            identity.authorize(
                session, agent, "ticket.reply", Resource("ticket", "TENANT_M03", group_id=group_id)
            )
    identity.update_member(admin, user_id, "AGENT", False)
    with pytest.raises(IdentityError):
        identity.authenticate(pair["access_token"])


def test_12_m03_database_constraints_and_downgrade_preservation(db):
    from sqlalchemy.exc import IntegrityError
    from ics_persistence.identity_schema import group_members, tenants

    with pytest.raises(IntegrityError):
        with db.transaction() as session:
            session.execute(
                insert(group_members).values(
                    tenant_id="TENANT_M03", group_id="UNKNOWN", user_id="ADMIN_M03"
                )
            )
    with pytest.raises(RuntimeError, match="non-empty"):
        migrate(db.engine, "base", downgrade=True)
    assert db.ready()
    with db.transaction() as session:
        assert (
            session.scalar(select(tenants.c.id).where(tenants.c.id == "TENANT_M03")) == "TENANT_M03"
        )


@pytest.fixture(scope="module")
def catalog_rows(db):
    """只写本轮临时数据库；两个店铺故意复用商品/SKU ID 和编码。"""
    from ics_persistence.identity_schema import organizations, tenants
    from ics_persistence.commerce_schema import categories, products, skus, prices, inventory

    stamp = dict(
        source="synthetic-erp",
        source_version=1,
        as_of=datetime(2026, 9, 13, 12, 0, 0, 123456),
        synced_at=datetime(2026, 9, 13, 12, 0, 0, 123456),
    )
    with db.transaction() as session:
        session.execute(insert(organizations).values(id="ORG_CATALOG", name="测试组织"))
        for tenant in ("CAT_A", "CAT_B"):
            session.execute(
                insert(tenants).values(
                    id=tenant, organization_id="ORG_CATALOG", name=tenant, active=True
                )
            )
            session.execute(
                insert(categories).values(tenant_id=tenant, id="C1", name="耳机", **stamp)
            )
            session.execute(
                insert(products).values(
                    tenant_id=tenant,
                    id="P1",
                    category_id="C1",
                    name="耳机",
                    description="合成商品",
                    status="ON_SALE",
                    **stamp,
                )
            )
            session.execute(
                insert(skus).values(
                    tenant_id=tenant,
                    id="S1",
                    product_id="P1",
                    code="BLACK",
                    specifications={"颜色": "黑色"},
                    status="ON_SALE",
                    **stamp,
                )
            )
            session.execute(
                insert(prices).values(
                    tenant_id=tenant,
                    sku_id="S1",
                    minor_units=29900,
                    currency="CNY",
                    valid_from=stamp["as_of"],
                    **stamp,
                )
            )
            session.execute(
                insert(inventory).values(
                    tenant_id=tenant,
                    sku_id="S1",
                    available_quantity=None if tenant == "CAT_A" else 0,
                    **stamp,
                )
            )
        session.execute(
            insert(products).values(
                tenant_id="CAT_A",
                id="ONLY_A",
                category_id="C1",
                name="A独有",
                description="",
                status="OFF_SHELF",
                **stamp,
            )
        )
    return stamp


def test_13_catalog_exact_money_unknown_stock_and_tenant_local_ids(db, catalog_rows):
    from ics_persistence.commerce_schema import prices, inventory, skus

    db.close()  # 连接池重开后读取，不能依赖 Python 内存中保存的值。
    with db.transaction() as session:
        assert (
            session.scalar(select(prices.c.as_of).where(prices.c.tenant_id == "CAT_A"))
            == catalog_rows["as_of"]
        )
        assert (
            session.scalar(select(prices.c.minor_units).where(prices.c.tenant_id == "CAT_A"))
            == 29900
        )
        rows = session.execute(select(inventory.c.tenant_id, inventory.c.available_quantity)).all()
        assert dict(rows) == {"CAT_A": None, "CAT_B": 0}
        assert len(session.execute(select(skus).where(skus.c.id == "S1")).all()) == 2


@pytest.mark.parametrize(
    "case",
    [
        "cross_tenant_product",
        "missing_sku",
        "duplicate_code",
        "negative_price",
        "unsafe_price",
        "lowercase_currency",
        "invalid_currency",
        "empty_price_window",
        "negative_inventory",
        "zero_version",
        "future_source",
        "invalid_status",
        "category_self",
    ],
)
def test_14_catalog_database_rejects_invalid_and_cross_tenant_rows(db, catalog_rows, case):
    from sqlalchemy.exc import DBAPIError
    from ics_persistence.commerce_schema import categories, products, skus, prices, inventory

    stamp = catalog_rows
    statements = {
        "cross_tenant_product": insert(skus).values(
            tenant_id="CAT_B",
            id="S_BAD",
            code="BAD",
            product_id="ONLY_A",
            specifications={},
            status="ON_SALE",
            **stamp,
        ),
        "missing_sku": insert(prices).values(
            tenant_id="CAT_A",
            sku_id="NO_SKU",
            minor_units=1,
            currency="CNY",
            valid_from=stamp["as_of"],
            **stamp,
        ),
        "duplicate_code": insert(skus).values(
            tenant_id="CAT_A",
            id="S_BAD",
            code="BLACK",
            product_id="P1",
            specifications={},
            status="ON_SALE",
            **stamp,
        ),
        "negative_price": update(prices).values(minor_units=-1),
        "unsafe_price": update(prices).values(minor_units=9007199254740992),
        "lowercase_currency": update(prices).values(currency="cny"),
        "invalid_currency": update(prices).values(currency="123"),
        "empty_price_window": update(prices).values(valid_until=stamp["as_of"]),
        "negative_inventory": update(inventory).values(available_quantity=-1),
        "zero_version": update(products).values(source_version=0),
        "future_source": update(products).values(as_of=datetime(2026, 9, 14)),
        "invalid_status": update(products).values(status="UNKNOWN"),
        "category_self": update(categories).values(parent_id="C1"),
    }
    statement = statements[case]
    if case not in {"cross_tenant_product", "missing_sku", "duplicate_code"}:
        statement = statement.where(statement.table.c.tenant_id == "CAT_A")
    # MySQL CHECK 返回 3819，PyMySQL 将它映射为 OperationalError 而非 IntegrityError。
    # 精确断言错误号，不能把断连或 SQL 语法错误当作约束测试通过。
    with pytest.raises(DBAPIError) as rejected:
        with db.transaction() as session:
            session.execute(statement)
    expected = (
        1062
        if case == "duplicate_code"
        else 1452
        if case in {"cross_tenant_product", "missing_sku"}
        else 3819
    )
    assert rejected.value.orig.args[0] == expected


def test_15_catalog_rows_and_schema_survive_refused_downgrade(db, catalog_rows):
    from sqlalchemy import inspect
    from ics_persistence.commerce_schema import TABLES, prices

    with pytest.raises(RuntimeError, match="non-empty"):
        migrate(db.engine, "base", downgrade=True)
    assert db.ready()
    assert {table.name for table in TABLES} <= set(inspect(db.engine).get_table_names())
    with db.transaction() as session:
        assert (
            session.scalar(select(prices.c.minor_units).where(prices.c.tenant_id == "CAT_A"))
            == 29900
        )
