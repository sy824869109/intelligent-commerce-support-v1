"""At-least-once publication primitives. Never publish while holding a DB transaction."""

from datetime import timedelta, timezone
import re
import uuid

from sqlalchemy import and_, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from .database import require_transaction
from .events import Event
from .schema import inbox, outbox


class EventConflict(Exception):
    """Stable event identity was reused with different content; no content in the error."""


def clock(session):
    # Use the database clock for leases across machines. MySQL sessions are initialized to UTC.
    value = session.scalar(select(func.current_timestamp()))
    return value.replace(tzinfo=None)


def identity(producer, tenant_id, event_id):
    return and_(
        outbox.c.producer == producer,
        outbox.c.tenant_id == tenant_id,
        outbox.c.event_id == event_id,
    )


def enqueue(session, event: Event, *, producer: str, tenant_id: str) -> bool:
    """Join the owner's existing transaction; False is same-event replay, not a new write."""
    require_transaction(session)
    if event.producer != producer or event.tenant_id != tenant_id:
        raise ValueError("Event ownership mismatch")
    values = event.model_dump()
    values["occurred_at"] = event.occurred_at.replace(tzinfo=None)
    digest = event.digest()
    try:
        with session.begin_nested():
            session.execute(
                insert(outbox).values(
                    **values,
                    payload_hash=digest,
                    status="PENDING",
                    attempts=0,
                    available_at=clock(session),
                )
            )
    except IntegrityError:
        # Locking read sees the committed winner under MySQL concurrent insert races.
        previous = session.scalar(
            select(outbox.c.payload_hash)
            .where(identity(producer, tenant_id, event.event_id))
            .with_for_update()
        )
        if previous != digest:
            raise EventConflict("Event identity conflict") from None
        return False
    return True


def claim(session, *, producer: str, batch_size=20, lease_seconds=30, max_attempts=5):
    """Return committed candidates to a caller that publishes AFTER leaving its transaction.

    MySQL SKIP LOCKED partitions work. Expired leases are recovered with new fencing tokens.
    This primitive does not promise aggregate ordering or consumer completion.
    """
    require_transaction(session)
    if not 1 <= batch_size <= 100 or not 5 <= lease_seconds <= 300 or not 1 <= max_attempts <= 20:
        raise ValueError("Invalid bounded relay policy")
    now = clock(session)
    candidates = (
        session.execute(
            select(outbox)
            .where(
                outbox.c.producer == producer,
                or_(
                    and_(outbox.c.status == "PENDING", outbox.c.available_at <= now),
                    and_(outbox.c.status == "LEASED", outbox.c.lease_until <= now),
                ),
            )
            .order_by(outbox.c.available_at, outbox.c.event_id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        .mappings()
        .all()
    )
    result = []
    for row in candidates:
        key = identity(row["producer"], row["tenant_id"], row["event_id"])
        if row["attempts"] >= max_attempts:
            session.execute(
                update(outbox)
                .where(key)
                .values(
                    status="DEAD",
                    lease_token=None,
                    lease_until=None,
                    last_error_code="RETRY_EXHAUSTED",
                )
            )
            continue
        token = uuid.uuid4().hex
        session.execute(
            update(outbox)
            .where(key)
            .values(
                status="LEASED",
                attempts=row["attempts"] + 1,
                lease_token=token,
                lease_until=now + timedelta(seconds=lease_seconds),
            )
        )
        event_data = {name: row[name] for name in Event.model_fields}
        event_data["occurred_at"] = row["occurred_at"].replace(tzinfo=timezone.utc)
        result.append((Event(**event_data), token))
    return result


def acknowledge(session, event: Event, token: str) -> bool:
    """Call only after the transport has durably accepted the event. Stale workers cannot ACK."""
    require_transaction(session)
    now = clock(session)
    result = session.execute(
        update(outbox)
        .where(
            identity(event.producer, event.tenant_id, event.event_id),
            outbox.c.status == "LEASED",
            outbox.c.lease_token == token,
            outbox.c.lease_until > now,
        )
        .values(status="PUBLISHED", published_at=now, lease_token=None, lease_until=None)
    )
    return result.rowcount == 1


def retry(session, event: Event, token: str, *, error_code="DELIVERY_FAILED", delay_seconds=5):
    """Persist bounded retry without changing the original ID or payload; never store raw errors."""
    require_transaction(session)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error_code) or not 1 <= delay_seconds <= 3600:
        raise ValueError("Invalid retry policy")
    now = clock(session)
    return (
        session.execute(
            update(outbox)
            .where(
                identity(event.producer, event.tenant_id, event.event_id),
                outbox.c.status == "LEASED",
                outbox.c.lease_token == token,
                outbox.c.lease_until > now,
            )
            .values(
                status="PENDING",
                available_at=now + timedelta(seconds=delay_seconds),
                lease_token=None,
                lease_until=None,
                last_error_code=error_code,
            )
        ).rowcount
        == 1
    )


def consume(
    session,
    event: Event,
    *,
    consumer: str,
    tenant_id: str,
    producer: str,
    event_type: str,
    schema_version: int,
    handler,
):
    """Inbox and handler writes share the caller's LOCAL transaction. Handler must not commit.

    No HTTP/model/queue side effects in handler. The returned reference is not durable until
    the surrounding transaction commits. Authenticate the source before calling this primitive.
    """
    require_transaction(session)
    # Even if the owner catches a handler failure, no empty Inbox reservation may commit.
    with session.begin_nested():
        return _consume(
            session,
            event,
            consumer=consumer,
            tenant_id=tenant_id,
            producer=producer,
            event_type=event_type,
            schema_version=schema_version,
            handler=handler,
        )


def _consume(session, event, *, consumer, tenant_id, producer, event_type, schema_version, handler):
    if (event.tenant_id, event.producer, event.event_type, event.schema_version) != (
        tenant_id,
        producer,
        event_type,
        schema_version,
    ):
        raise ValueError("Unsupported event scope or schema")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}", consumer):
        raise ValueError("Invalid consumer")
    key = and_(
        inbox.c.consumer == consumer,
        inbox.c.tenant_id == tenant_id,
        inbox.c.event_id == event.event_id,
    )
    try:
        with session.begin_nested():
            session.execute(
                insert(inbox).values(
                    consumer=consumer,
                    tenant_id=tenant_id,
                    event_id=event.event_id,
                    payload_hash=event.digest(),
                    result_ref="",
                    processed_at=clock(session),
                )
            )
    except IntegrityError:
        previous = session.execute(select(inbox).where(key).with_for_update()).mappings().one()
        if previous["payload_hash"] != event.digest():
            raise EventConflict("Inbox event identity conflict") from None
        return previous["result_ref"]
    # A failed handler must escape and roll back the owner transaction, including the Inbox.
    result = handler(session, event)
    if not isinstance(result, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", result
    ):
        raise ValueError("Handler must return an opaque durable result reference")
    session.execute(update(inbox).where(key).values(result_ref=result))
    return result
