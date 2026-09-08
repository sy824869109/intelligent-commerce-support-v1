import asyncio
import json
import logging
import re

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ics_gateway.app import create_app
from ics_gateway.settings import Settings


def test_health_and_lifecycle():
    app = create_app(Settings(environment="test"))
    assert app.state.ready is False
    with TestClient(app) as client:
        for endpoint in ("live", "ready"):
            r = client.get(f"/health/{endpoint}")
            assert r.status_code == 200
            assert r.json()["data"]["scope"] == "application"
            assert set(r.json()) == {"request_id", "trace_id", "data"}
            assert r.json()["request_id"] == r.headers["x-request-id"]
            assert r.json()["trace_id"] == r.headers["x-trace-id"]
        assert client.get("/health/ready").json()["data"]["checks"] == {"lifecycle": "ok"}
    assert app.state.ready is False


def test_without_lifespan_not_ready():
    with TestClient(create_app()) as client:
        client.app.state.ready = False
        assert client.get("/health/ready").status_code == 503
        assert client.get("/health/live").status_code == 200


@pytest.mark.parametrize("candidate", ["good-REQ_001", "", "a" * 65, "bad value", "bad\r\nvalue"])
def test_request_id_validation(candidate):
    with TestClient(create_app()) as client:
        r = client.get("/health/live", headers={"X-Request-ID": candidate})
        actual = r.headers["x-request-id"]
        assert (
            actual == candidate
            if candidate == "good-REQ_001"
            else re.fullmatch(r"[0-9a-f]{32}", actual)
        )


def test_duplicate_and_untrusted_trace_headers():
    with TestClient(create_app()) as client:
        r = client.get(
            "/health/live",
            headers=[
                ("x-request-id", "first"),
                ("x-request-id", "second"),
                ("x-trace-id", "untrusted"),
            ],
        )
        assert r.headers["x-request-id"] not in {"first", "second"}
        assert r.headers["x-trace-id"] != "untrusted"


@pytest.mark.parametrize(
    "method,path,status,code",
    [("get", "/missing", 404, "NOT_FOUND"), ("post", "/health/live", 405, "METHOD_NOT_ALLOWED")],
)
def test_http_errors(method, path, status, code):
    with TestClient(create_app()) as client:
        r = getattr(client, method)(path)
        assert r.status_code == status
        assert r.json()["error"]["code"] == code
        assert "data" not in r.json()
        assert r.headers["cache-control"] == "no-store"
        if status == 405:
            assert "GET" in r.headers["allow"]


def test_validation_http_and_unexpected_errors_are_redacted(caplog):
    app = create_app()

    @app.get("/testing/number")
    async def number(value: int):
        return value

    @app.get("/testing/failure")
    async def unexpected():
        raise RuntimeError("secret-fixture-password")

    @app.get("/testing/forbidden")
    async def forbidden():
        raise HTTPException(403, detail="secret-fixture-password")

    caplog.set_level(logging.INFO, logger="ics.gateway.requests")
    with TestClient(app) as client:
        for path, status in [
            ("/testing/number?value=secret-fixture-password", 422),
            ("/testing/failure", 500),
            ("/testing/forbidden", 403),
        ]:
            r = client.get(path, headers={"authorization": "Bearer secret-fixture-password"})
            assert r.status_code == status
            assert "secret-fixture-password" not in r.text
            assert r.json()["request_id"] == r.headers["x-request-id"]
        assert client.get("/health/live").status_code == 200
    records = [json.loads(r.message) for r in caplog.records if r.name == "ics.gateway.requests"]
    assert [r["status"] for r in records] == [422, 500, 403, 200]
    assert "secret-fixture-password" not in json.dumps(records)


@pytest.mark.parametrize("mode", ["false", "error", "timeout", "true"])
def test_dependency_extension_bounded_and_fail_closed(mode):
    async def check():
        if mode == "error":
            raise RuntimeError("private endpoint")
        if mode == "timeout":
            await asyncio.sleep(10)
        return mode == "true"

    app = create_app(Settings(readiness_timeout_seconds=0.02), checks={"synthetic": check})
    with TestClient(app) as client:
        r = client.get("/health/ready")
        assert r.status_code == (200 if mode == "true" else 503)
        assert "private endpoint" not in r.text
        assert client.get("/health/live").status_code == 200


def test_concurrent_requests_do_not_share_context():
    async def run():
        app = create_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                rs = await asyncio.gather(
                    *(
                        client.get("/health/live", headers={"x-request-id": f"req-{i}"})
                        for i in range(20)
                    )
                )
                assert [r.json()["request_id"] for r in rs] == [f"req-{i}" for i in range(20)]
                assert len({r.json()["trace_id"] for r in rs}) == 20

    asyncio.run(run())


def test_factory_isolation_and_docs():
    one, two = create_app(), create_app(Settings(docs_enabled=False))
    with TestClient(one) as c1, TestClient(two) as c2:
        one.state.ready = False
        assert c2.get("/health/ready").status_code == 200
        schema = c1.get("/openapi.json").json()
        assert schema["openapi"].startswith("3.1")
        assert set(schema["paths"]) == {"/health/live", "/health/ready"}
        assert "503" in schema["paths"]["/health/ready"]["get"]["responses"]
        assert c1.get("/docs").status_code == 200
        assert c2.get("/docs").status_code == 404
        assert c2.get("/openapi.json").status_code == 404


@pytest.mark.parametrize(
    "fields",
    [
        {"environment": "prod"},
        {"port": 23306},
        {"port": 0},
        {"host": "0.0.0.0"},
        {"readiness_timeout_seconds": 0},
        {"readiness_timeout_seconds": 6},
    ],
)
def test_invalid_settings(fields):
    with pytest.raises(ValidationError):
        Settings(**fields)


def test_only_namespaced_environment(monkeypatch):
    monkeypatch.setenv("APP_PORT", "8000")
    monkeypatch.setenv("ICS_GATEWAY_PORT", "28001")
    assert Settings().port == 28001
