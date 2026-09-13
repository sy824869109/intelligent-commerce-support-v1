"""Audit the unified lock, including CPU builds that pip-audit otherwise skips."""

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess  # nosec B404
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "_local_artifacts/environment"
LOCK = ROOT / "deploy/dev-environment/v1-requirements.lock"


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    REPORTS.mkdir(parents=True, exist_ok=True)
    # Fixed interpreter and repository lock; shell interpolation is never used.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--no-deps",
            "--disable-pip",
            "-r",
            str(LOCK),
            "--cache-dir",
            str(ROOT / "_local_artifacts/caches/pip-audit"),
            "--format",
            "json",
            "--output",
            str(REPORTS / "python-audit.json"),
        ],
        cwd=ROOT,
    )  # nosec B603
    if result.returncode:
        return 1
    report = json.loads((REPORTS / "python-audit.json").read_text(encoding="utf-8"))
    skipped = {item["name"] for item in report["dependencies"] if item.get("skip_reason")}
    if skipped - {"torch", "torchvision"}:
        print("Dependency audit incomplete: unexpected skipped packages")
        return 1
    cpu_results = {}
    content = LOCK.read_text(encoding="utf-8")
    for name in ("torch", "torchvision"):
        match = re.search(rf"(?m)^{name}==([0-9.]+)\+cpu", content)
        if not match:
            raise ValueError("CPU runtime identity missing")
        version = match.group(1)
        # Names are fixed; version is digits/dots from reviewed lock, HTTPS only.
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{name}/{version}/json", timeout=60
        ) as response:  # nosec B310
            metadata = json.load(response)
        cpu_results[name] = {
            "version": version,
            "vulnerabilities": metadata.get("vulnerabilities", []),
        }
        if metadata.get("vulnerabilities") or all(item.get("yanked") for item in metadata["urls"]):
            print("CPU package public release audit failed")
            return 1
    record = {
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "PASS",
        "cpu_public_release_checks": cpu_results,
        "scope": "Known dependency advisories, not OS signing or model quality",
    }
    (REPORTS / "python-audit-complete.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    print("Unified Python audit PASS; CPU public-version advisories also checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
