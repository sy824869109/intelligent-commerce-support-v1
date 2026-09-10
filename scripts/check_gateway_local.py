"""Exercise a temporary loopback gateway with the ownership-checked platform database."""

import json
import os
from pathlib import Path
import socket
# Fixed local test child, no shell or caller command input.
import subprocess  # nosec B404
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    # A test-only ephemeral port; do not stop or replace any existing listener.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
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
                    f"http://127.0.0.1:{port}/health/ready",
                    headers={"X-Request-ID": "M02-local-probe"},
                )
                # Literal loopback origin only; bypass inherited proxy settings.
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
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
    print("M02 local HTTP + MySQL readiness + trace + structured log PASS; owned gateway stopped.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("M02 gateway probe failed; internal configuration and process logs withheld.")
        raise SystemExit(1) from None
