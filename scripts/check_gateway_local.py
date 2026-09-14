"""Exercise a temporary loopback gateway with the ownership-checked platform database."""

import json
import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
import socket
import ssl

# Fixed local test child, no shell or caller command input.
import subprocess  # nosec B404
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tls-entry", action="store_true", help="Check the owned Nginx TLS entry")
    args = parser.parse_args()
    # A test-only ephemeral port; do not stop or replace any existing listener.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 28000 if args.tls_entry else 0))
        port = reservation.getsockname()[1]
    base = "https://localhost:28443" if args.tls_entry else f"http://127.0.0.1:{port}"
    handlers = [urllib.request.ProxyHandler({})]
    if args.tls_entry:
        context = ssl.create_default_context(
            cafile=str(ROOT / "_local_artifacts/environment/secrets/server.pem")
        )
        handlers.append(urllib.request.HTTPSHandler(context=context))
    opener = urllib.request.build_opener(*handlers)
    environment = os.environ.copy()
    environment.update(
        ICS_GATEWAY_HOST="127.0.0.1", ICS_GATEWAY_PORT=str(port), PYTHONDONTWRITEBYTECODE="1"
    )
    # Interpreter + fixed repository script/flag only; terminate the owned handle only.
    process = subprocess.Popen(  # nosec B603
        [sys.executable, "scripts/run_gateway.py", "--with-database"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    output = b""
    try:
        deadline = time.monotonic() + 30
        while True:
            if process.poll() is not None:
                raise RuntimeError("Owned gateway exited before readiness")
            try:
                request = urllib.request.Request(
                    base + "/health/ready",
                    headers={"X-Request-ID": "M02-local-probe"},
                )
                # Literal loopback origin only; bypass inherited proxy settings.
                with opener.open(request, timeout=2) as response:
                    body = json.loads(response.read(8192))
                    if (
                        body["data"]["checks"].get("mysql") != "ok"
                        or body["request_id"] != "M02-local-probe"
                        or body["trace_id"] != response.headers["X-Trace-ID"]
                    ):
                        raise RuntimeError("Readiness/correlation mismatch")
                break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Gateway readiness deadline exceeded") from None
                time.sleep(0.2)
        # M03 is enabled by --with-database; no seeded identity is needed for denial testing.
        denied = False
        try:
            with opener.open(base + "/api/v1/auth/me", timeout=2):
                raise RuntimeError("Anonymous identity request unexpectedly succeeded")
        except urllib.error.HTTPError as exc:
            with exc:
                body = json.loads(exc.read(8192))
                denied = exc.code == 401 and body.get("error", {}).get("code") == "AUTH_REQUIRED"
        if not denied:
            raise RuntimeError("Identity denial contract mismatch")
        for path in (
            "/api/v1/products",
            "/api/v1/products/P1",
            "/api/v1/products/P1/specifications",
            "/api/v1/products/P1/skus/S1",
            "/api/v1/products/P1/activity",
        ):
            try:
                with opener.open(base + path, timeout=2):
                    raise RuntimeError("Anonymous catalog request unexpectedly succeeded")
            except urllib.error.HTTPError as exc:
                with exc:
                    body = json.loads(exc.read(8192))
                    if exc.code != 401 or body.get("error", {}).get("code") != "AUTH_REQUIRED":
                        raise RuntimeError("Catalog denial contract mismatch") from None
    finally:
        # Exact owned child only; never kill by port or process name.
        if process.poll() is None:
            process.terminate()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=5)
    lines = output.decode("utf-8", errors="replace").splitlines()
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    if not any(
        isinstance(row, dict)
        and row.get("request_id") == "M02-local-probe"
        and row.get("outcome") == "SUCCEEDED"
        for row in events
    ):
        raise RuntimeError("Owned process did not emit correlated success log")
    print(
        "M02/M03/M04 local HTTP + MySQL + trace + log + identity/catalog anonymous denial PASS; owned gateway stopped."
    )
    if args.tls_entry:
        destination = ROOT / "_local_artifacts/environment/check-gateway-tls.json"
        destination.write_text(
            json.dumps(
                {
                    "checked_at": datetime.now(UTC).isoformat(),
                    "status": "PASS",
                    "tls_certificate": "VERIFIED",
                    "proxy_to_gateway": "PASS",
                    "mysql": "PASS",
                    "anonymous_identity": "401 AUTH_REQUIRED",
                    "correlated_log": "PASS",
                    "owned_gateway_stopped": True,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("M02 gateway probe failed; internal configuration and process logs withheld.")
        raise SystemExit(1) from None
