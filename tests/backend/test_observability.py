"""No collector, file sink, HTTP metrics endpoint or real business audit is used."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages/observability"))
from ics_observability.core import AuditRecord, CURRENT, Metrics, diagnostic, trace_scope


def test_trace_nested_and_exception_reset():
    assert CURRENT.get() is None
    with trace_scope("REQ1") as first:
        with pytest.raises(RuntimeError):
            with trace_scope("REQ2") as second:
                assert first.trace_id != second.trace_id
                raise RuntimeError("test")
        assert CURRENT.get() == first
    assert CURRENT.get() is None


def test_concurrent_trace_isolation():
    async def worker(name):
        with trace_scope(name):
            await asyncio.sleep(0)
            return CURRENT.get().request_id

    async def run():
        return await asyncio.gather(worker("A"), worker("B"))

    assert asyncio.run(run()) == ["A", "B"]
    assert CURRENT.get() is None


def test_diagnostics_allowlist_and_correlation():
    with trace_scope("REQ1") as trace:
        value = json.loads(diagnostic("operation_finished", "FAILED"))
        assert value["trace_id"] == trace.trace_id
        assert set(value) == {"event", "outcome", "timestamp", "request_id", "trace_id"}
    with pytest.raises(ValueError):
        diagnostic("secret customer payload", "FAILED")


@pytest.mark.parametrize("duration", [-1, float("inf"), float("nan"), True, "10"])
def test_metrics_reject_bad_durations(duration):
    with pytest.raises(ValueError):
        Metrics(["health"]).observe("health", "SUCCEEDED", duration)


def test_metrics_bounded_labels_and_buckets():
    metrics = Metrics(["health"])
    for duration in (0, 10, 11, 5001):
        metrics.observe("health", "SUCCEEDED", duration)
    snapshot = metrics.snapshot()
    assert snapshot[("health", "SUCCEEDED")] == (2, 1, 0, 0, 0, 0, 1)
    snapshot.clear()
    assert len(metrics.snapshot()) == 3
    with pytest.raises(ValueError):
        metrics.observe("customer-id", "SUCCEEDED", 1)
    with pytest.raises(ValueError):
        Metrics([str(i) for i in range(65)])


def test_audit_strict_references_and_utc():
    fields = dict(
        event_id="E1",
        actor_ref="A1",
        tenant_ref="T1",
        target_ref="O1",
        request_id="R1",
        trace_id="TRACE1",
        action="ACCESS_CHECK",
        outcome="DENIED",
        occurred_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    assert json.loads(AuditRecord(**fields).to_json())["outcome"] == "DENIED"
    for change in (
        {"actor_ref": "a\nsecret"},
        {"action": "arbitrary text"},
        {"occurred_at": datetime(2026, 9, 10)},
    ):
        with pytest.raises(ValueError):
            AuditRecord(**(fields | change))
    with pytest.raises(TypeError):
        AuditRecord(**fields, password="not-accepted")
