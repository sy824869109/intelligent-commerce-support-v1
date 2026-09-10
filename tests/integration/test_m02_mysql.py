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
