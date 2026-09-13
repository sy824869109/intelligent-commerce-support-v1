"""Validate loopback gRPC protocol and authenticated Grafana datasource health.

Empty protobuf Export requests validate transport/service dispatch only. Actual
signal persistence is checked separately by check_environment.py telemetry.
No OTel Python instrumentation SDK or business integration is implied.
"""

from datetime import UTC, datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "_local_artifacts/environment"


def verify():
    import grpc
    import httpx
    from environment_services import health

    health()
    protocols = {}
    # Explicit insecure gRPC is confined to this same-host diagnostic endpoint.
    with grpc.insecure_channel(
        "127.0.0.1:24317", options=(("grpc.enable_http_proxy", 0),)
    ) as channel:
        for signal, service in (("trace", "Trace"), ("metrics", "Metrics"), ("logs", "Logs")):
            call = channel.unary_unary(
                f"/opentelemetry.proto.collector.{signal}.v1.{service}Service/Export"
            )
            # Some receivers serialize the optional empty partial_success message.
            # Both encodings mean zero rejected items and no error message.
            if call(b"", timeout=10) not in (b"", b"\x0a\x00"):
                raise ValueError("Unexpected empty export response")
            protocols[signal] = "PASS_EMPTY_EXPORT"
    secret = LOCAL / "secrets/grafana_password"
    if secret.is_symlink():
        raise ValueError("Secret cannot be a link")
    password = secret.read_text(encoding="utf-8").strip()
    with httpx.Client(
        base_url="http://127.0.0.1:23000", timeout=15, follow_redirects=False, trust_env=False
    ) as client:
        if client.get("/api/datasources").status_code != 401:
            raise ValueError("Grafana must reject anonymous datasource access")
        client.auth = httpx.BasicAuth("admin", password)
        response = client.get("/api/datasources")
        response.raise_for_status()
        sources = response.json()
        if {source["type"] for source in sources} != {"prometheus", "tempo", "loki"}:
            raise ValueError("Unexpected datasource scope")
        statuses = {}
        for source in sources:
            uid = source["uid"]
            if not uid.replace("-", "").replace("_", "").isalnum():
                raise ValueError("Unexpected datasource identifier")
            response = client.get(f"/api/datasources/uid/{uid}/health")
            response.raise_for_status()
            if response.json().get("status") != "OK":
                raise ValueError("Datasource health check failed")
            statuses[source["type"]] = "PASS"
    return {
        "grpc": protocols,
        "grafana_anonymous": "401",
        "grafana_datasources": statuses,
        "business_instrumentation": "NOT_IMPLEMENTED",
    }


def main():
    result = {"checked_at": datetime.now(UTC).isoformat()}
    try:
        result.update(status="PASS", details=verify())
    except Exception as exc:
        # Never print provider bodies, HTTP headers or secret-bearing exceptions.
        result.update(status="FAILED", error_type=type(exc).__name__)
    (LOCAL / "check-telemetry-access.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
