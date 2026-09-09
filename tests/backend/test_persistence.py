"""Portable behavioral tests; SQLite does NOT certify MySQL locking or DDL behavior."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from ics_gateway.app import create_app
from ics_persistence.database import Database, DatabaseConfig
from ics_persistence.events import Event
from ics_persistence.migration import migrate
from ics_persistence.outbox import acknowledge, claim, consume, enqueue, EventConflict, retry
from ics_persistence.schema import inbox, outbox


def event(**overrides):
    return Event(
        **{
            "event_id": "EV001",
            "event_type": "synthetic.created",
            "producer": "test-producer",
            "tenant_id": "TENANT_A",
            "aggregate_type": "synthetic",
            "aggregate_id": "S001",
            "aggregate_version": 1,
            "occurred_at": datetime(2026, 9, 9, tzinfo=timezone.utc),
            "correlation_id": "C001",
            "causation_id": "CMD001",
            "trace_id": "TR001",
            "payload": {"content_ref": "REF001"},
            **overrides,
        }
    )


@pytest.fixture
def database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False, "autocommit": False},
        poolclass=StaticPool,
    )
    db = Database(engine)
    migrate(engine)
    yield db
    db.close()


def put(session, item=None):
    return enqueue(session, item or event(), producer="test-producer", tenant_id="TENANT_A")


def accept(session, item=None, handler=lambda s, e: "REF001", **overrides):
    arguments = dict(
        consumer="test-consumer",
        tenant_id="TENANT_A",
        producer="test-producer",
        event_type="synthetic.created",
        schema_version=1,
        handler=handler,
    )
    arguments.update(overrides)
    return consume(session, item or event(), **arguments)


def test_upgrade_idempotent_empty_downgrade_and_reupgrade(database):
    assert database.ready()
    migrate(database.engine)
    migrate(database.engine, "base", downgrade=True)
    assert not database.ready()
    migrate(database.engine)
    assert database.ready()


def test_nonempty_downgrade_refused(database):
    with database.transaction() as session:
        put(session)
    with pytest.raises(RuntimeError, match="non-empty"):
        migrate(database.engine, "base", downgrade=True)
    assert database.ready()


def test_commit_rollback_and_closed_session(database):
    with pytest.raises(RuntimeError):
        with database.transaction() as session:
            put(session)
            raise RuntimeError("synthetic")
    with database.transaction() as session:
        assert session.execute(select(outbox)).first() is None
        assert put(session)
    with pytest.raises(InvalidRequestError):
        session.execute(select(outbox))


def test_no_implicit_transaction(database):
    with database.sessions() as session:
        with pytest.raises(RuntimeError, match="explicit"):
            put(session)


def test_enqueue_identity_conflict_and_tenant_guard(database):
    with database.transaction() as session:
        assert put(session)
        assert not put(session)
        with pytest.raises(EventConflict):
            put(session, event(payload={"content_ref": "OTHER"}))
        with pytest.raises(ValueError, match="ownership"):
            put(session, event(tenant_id="TENANT_B"))
        assert len(session.execute(select(outbox)).all()) == 1


def test_lease_ack_is_fenced_and_not_consumer_completion(database):
    with database.transaction() as session:
        put(session)
    with database.transaction() as session:
        assert claim(session, producer="other-producer") == []
        [(item, token)] = claim(session, producer="test-producer")
    with database.transaction() as session:
        assert claim(session, producer="test-producer") == []
        assert not acknowledge(session, item, "stale")
        assert acknowledge(session, item, token)
        assert not acknowledge(session, item, token)
        assert session.execute(select(inbox)).first() is None


def test_retry_preserves_identity_and_backoff(database):
    with database.transaction() as session:
        put(session)
        [(item, token)] = claim(session, producer="test-producer")
        assert retry(session, item, token, delay_seconds=100)
        assert claim(session, producer="test-producer") == []
        row = session.execute(select(outbox)).mappings().one()
        assert row["event_id"] == "EV001" and row["attempts"] == 1


def test_inbox_dedup_and_conflict(database):
    calls = []

    def handle(session, item):
        calls.append(item.event_id)
        return "RESULT001"

    with database.transaction() as session:
        assert accept(session, handler=handle) == "RESULT001"
        assert accept(session, handler=handle) == "RESULT001"
        with pytest.raises(EventConflict):
            accept(session, event(payload={"content_ref": "DIFFERENT"}))
    assert calls == ["EV001"]


def test_inbox_failure_even_if_caught_leaves_no_reservation(database):
    def fail(session, item):
        put(session)
        raise RuntimeError("handler failed")

    with database.transaction() as session:
        with pytest.raises(RuntimeError):
            accept(session, handler=fail)
        assert session.execute(select(inbox)).first() is None
        assert session.execute(select(outbox)).first() is None
        assert accept(session) == "REF001"


@pytest.mark.parametrize(
    "override",
    [
        {"tenant_id": "TENANT_B"},
        {"producer": "unknown"},
        {"event_type": "unknown"},
        {"schema_version": 2},
        {"consumer": "invalid consumer"},
    ],
)
def test_consumer_scope_rejected(database, override):
    with database.transaction() as session, pytest.raises(ValueError):
        accept(session, **override)


@pytest.mark.parametrize(
    "override",
    [
        {"occurred_at": datetime(2026, 9, 9)},
        {"payload": {"data": "x" * 17000}},
        {"schema_version": 0},
        {"aggregate_version": 0},
        {"event_id": "bad id"},
        {"payload": {"amount": float("nan")}},
    ],
)
def test_event_validation(override):
    with pytest.raises(ValueError):
        event(**override)


def test_database_credentials_repr_and_target_guard():
    config = DatabaseConfig(username="app", password="synthetic-secret", database="test")
    assert "synthetic-secret" not in repr(config)
    assert "synthetic-secret" not in str(config.url())
    with pytest.raises(ValueError):
        DatabaseConfig(username="app", password="x", database="test", host="remote").url()


def test_database_gateway_readiness_and_version_failure(database):
    with TestClient(create_app(database=database)) as client:
        ready = client.get("/health/ready").json()["data"]
        assert ready["scope"] == "application+database" and ready["checks"]["mysql"] == "ok"
        migrate(database.engine, "base", downgrade=True)
        assert client.get("/health/ready").status_code == 503
        assert client.get("/health/live").status_code == 200
