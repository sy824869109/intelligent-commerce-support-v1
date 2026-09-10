"""ASGI streaming, trace/log/metric integration and atomic audit failure semantics."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from ics_gateway.app import create_app
from ics_gateway.middleware import RequestContext
from ics_observability.core import AuditRecord, CURRENT, Metrics
from ics_observability.audit import append_audit, AuditConflict
from ics_persistence.database import Database
from ics_persistence.migration import migrate
from ics_persistence.schema import audit
from ics_contracts.events import encode_sse


def record():
    return AuditRecord(
        "E1",
        "A1",
        "T1",
        "O1",
        "REQ1",
        "TRACE1",
        "COMMAND_SUBMIT",
        "SUCCEEDED",
        datetime(2026, 9, 10, tzinfo=timezone.utc),
    )


def test_gateway_metrics_trace_and_logs(caplog):
    app = create_app()

    @app.get("/test/context")
    async def context():
        return {"trace": CURRENT.get().trace_id}

    with caplog.at_level(logging.INFO, logger="ics.gateway.requests"), TestClient(app) as client:
        result = client.get("/test/context?private=do-not-log")
        assert result.json()["trace"] == result.headers["x-trace-id"]
        assert client.get("/not-found").status_code == 404
    data = json.loads(app.state.metrics.to_json())
    counts = {row["outcome"]: sum(row["counts"]) for row in data["series"]}
    assert counts == {"SUCCEEDED": 1, "FAILED": 1, "CANCELLED": 0}
    assert "do-not-log" not in caplog.text
    assert "response_complete" in caplog.text
    assert CURRENT.get() is None


@pytest.mark.parametrize("mode", ["complete", "failure", "cancel", "send_failure"])
def test_stream_frames_not_buffered_and_context_reset(mode):
    metrics, sent = Metrics(["http"]), []
    frame = encode_sse(
        {
            "schema_version": 1,
            "conversation_id": "C1",
            "control_epoch": 0,
            "event_type": "answer.delta",
            "run_id": "R1",
            "token_seq": 1,
            "text": "你好",
        }
    )

    async def stream(scope, receive, send):
        assert CURRENT.get() is not None
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/event-stream")],
            }
        )
        await send({"type": "http.response.body", "body": frame, "more_body": True})
        assert sent[-1]["body"] == frame
        if mode == "failure":
            raise RuntimeError("private upstream text")
        if mode == "cancel":
            raise asyncio.CancelledError()
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        if mode == "send_failure" and message["type"] == "http.response.body":
            raise OSError("disconnect")
        sent.append(message)

    async def run():
        scope = {"type": "http", "method": "GET", "path": "/synthetic-stream", "headers": []}
        try:
            await RequestContext(stream, metrics)(scope, receive, send)
        finally:
            assert CURRENT.get() is None

    if mode == "complete":
        asyncio.run(run())
    else:
        with pytest.raises((RuntimeError, asyncio.CancelledError, OSError)):
            asyncio.run(run())
    assert len([item for item in sent if item["type"] == "http.response.start"]) == 1
    outcome = "SUCCEEDED" if mode == "complete" else "CANCELLED" if mode == "cancel" else "FAILED"
    assert sum(metrics.snapshot()[("http", outcome)]) == 1


def test_audit_commit_reopen_retry_rollback_and_failure(tmp_path):
    path = tmp_path / "audit-test.sqlite"
    db = Database(create_engine("sqlite:///" + path.as_posix(), connect_args={"autocommit": False}))
    migrate(db.engine)
    try:
        with pytest.raises(RuntimeError):
            with db.transaction() as session:
                append_audit(session, record(), tenant_ref="T1")
                raise RuntimeError("rollback owner transaction")
        with db.transaction() as session:
            assert session.execute(select(audit)).first() is None
            assert append_audit(session, record(), tenant_ref="T1")
        db.close()
        with db.transaction() as session:
            assert not append_audit(session, record(), tenant_ref="T1")
        with pytest.raises(AuditConflict):
            with db.transaction() as session:
                append_audit(session, replace(record(), event_id="E2"), tenant_ref="T1")
                append_audit(session, replace(record(), outcome="FAILED"), tenant_ref="T1")
        with db.transaction() as session:
            assert len(session.execute(select(audit)).all()) == 1
            with pytest.raises(ValueError, match="tenant"):
                append_audit(session, record(), tenant_ref="T2")
        with pytest.raises(RuntimeError, match="non-empty"):
            migrate(db.engine, "base", downgrade=True)
    finally:
        db.close()


def test_diagnostic_sink_failure_does_not_change_response(monkeypatch):
    from ics_gateway.middleware import LOGGER

    def broken(*args, **kwargs):
        raise OSError("diagnostic sink unavailable")

    monkeypatch.setattr(LOGGER, "info", broken)
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
    assert sum(app.state.metrics.snapshot()[("http", "SUCCEEDED")]) == 1
    assert CURRENT.get() is None
