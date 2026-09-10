"""Bounded diagnostic primitives with explicit trust and persistence boundaries."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import re
from threading import Lock
from uuid import uuid4

IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid diagnostic reference")
    return value


@dataclass(frozen=True)
class Trace:
    request_id: str
    trace_id: str

    def __post_init__(self):
        identifier(self.request_id)
        identifier(self.trace_id)


CURRENT: ContextVar[Trace | None] = ContextVar("ics_trace", default=None)


@contextmanager
def trace_scope(request_id: str):
    """Generate a local trace, not a W3C/OpenTelemetry span or authorization identity.

    Reset in finally prevents request leakage on errors; child tasks inherit context.
    Explicit trusted propagation across process/queue boundaries is not implemented.
    """
    trace = Trace(request_id=identifier(request_id), trace_id=uuid4().hex)
    token = CURRENT.set(trace)
    try:
        yield trace
    finally:
        CURRENT.reset(token)


def diagnostic(event: str, outcome: str) -> str:
    """No arbitrary attributes, free-text messages, payloads or exception strings."""
    if event not in {"operation_started", "operation_finished", "dependency_check"}:
        raise ValueError("Unknown diagnostic event")
    if outcome not in {"STARTED", "SUCCEEDED", "FAILED", "CANCELLED"}:
        raise ValueError("Unknown outcome")
    trace = CURRENT.get()
    return json.dumps(
        {
            "event": event,
            "outcome": outcome,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": trace.request_id if trace else None,
            "trace_id": trace.trace_id if trace else None,
        },
        sort_keys=True,
    )


class Metrics:
    """Per-instance counters and fixed latency buckets; no user-defined labels.

    Registered operation names must be static deployment configuration, never IDs
    derived from requests. Snapshot is a copy, not a metrics endpoint or exporter.
    """

    BOUNDS = (10.0, 50.0, 100.0, 500.0, 1000.0, 5000.0)

    def __init__(self, operations):
        names = tuple(operations)
        if not 1 <= len(names) <= 64 or len(set(names)) != len(names):
            raise ValueError("Register 1..64 unique static operations")
        for name in names:
            identifier(name)
        self._values = {
            (name, result): [0] * 7
            for name in names
            for result in ("SUCCEEDED", "FAILED", "CANCELLED")
        }
        self._lock = Lock()

    def observe(self, operation: str, outcome: str, duration_ms: float):
        key = (operation, outcome)
        if key not in self._values:
            raise ValueError("Unregistered metric label")
        if (
            type(duration_ms) not in (int, float)
            or not math.isfinite(duration_ms)
            or duration_ms < 0
        ):
            raise ValueError("Invalid duration")
        bucket = next((i for i, upper in enumerate(self.BOUNDS) if duration_ms <= upper), 6)
        with self._lock:
            self._values[key][bucket] += 1

    def snapshot(self):
        # Noncumulative bucket counts: <=10, (10,50], ..., >5000 ms.
        with self._lock:
            return {key: tuple(value) for key, value in self._values.items()}


@dataclass(frozen=True)
class AuditRecord:
    """Server-created references only; never accept this object as client authority.

    Durable atomic writing, retention, access control and tamper evidence belong to
    a future sink. Serialization alone must never acknowledge audit persistence.
    """

    event_id: str
    actor_ref: str
    tenant_ref: str
    target_ref: str
    request_id: str
    trace_id: str
    action: str
    outcome: str
    occurred_at: datetime

    def __post_init__(self):
        for name in ("event_id", "actor_ref", "tenant_ref", "target_ref", "request_id", "trace_id"):
            identifier(getattr(self, name))
        if self.action not in {
            "ACCESS_CHECK",
            "COMMAND_SUBMIT",
            "KNOWLEDGE_PUBLISH",
            "TICKET_ASSIGN",
        }:
            raise ValueError("Unregistered audit action")
        if self.outcome not in {"ALLOWED", "DENIED", "SUCCEEDED", "FAILED"}:
            raise ValueError("Unregistered audit outcome")
        if not isinstance(self.occurred_at, datetime) or self.occurred_at.utcoffset() is None:
            raise ValueError("Audit timestamp must include timezone")

    def to_json(self):
        value = asdict(self)
        value["occurred_at"] = self.occurred_at.astimezone(timezone.utc).isoformat()
        return json.dumps(value, sort_keys=True)
