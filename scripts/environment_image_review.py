"""Exact artifact-bound review of two upstream-fixed Tempo pseudo-version findings.

The scanner is never given ignore flags. Raw results remain unchanged. Any other
artifact, package version, CVE or missing binary identity remains unresolved.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "deploy/dev-environment/security/grafana-reviewed-fixes.json"
ALLOWED = {"CVE-2026-21728", "CVE-2026-28377"}


def review_findings(identity, findings):
    raw = REVIEW.read_bytes()
    rule = json.loads(raw)
    if rule["schema_version"] != 1 or set(rule["fixes"]) != ALLOWED or not rule["approval"]:
        raise ValueError("Unexpected reviewed-fix scope")
    matches = (
        identity.get("image_id") == rule["image_id"]
        and identity.get("config_id") == rule["config_id"]
        and identity.get("binary_sha256", {}).get(rule["binary_path"]) == rule["binary_sha256"]
    )
    reviewed, unresolved = [], []
    for finding in findings:
        fix = rule["fixes"].get(finding["VulnerabilityID"])
        if (
            matches
            and fix
            and fix["comparison_status"] == "ahead"
            and fix["behind_by"] == 0
            and finding.get("Target") == rule["binary_path"]
            and finding["PkgName"] == rule["package"]
            and finding["InstalledVersion"] == rule["version"]
        ):
            reviewed.append(finding)
        else:
            unresolved.append(finding)
    return {
        "review_sha256": hashlib.sha256(raw).hexdigest(),
        "reviewed_fixes": sorted({v["VulnerabilityID"] for v in reviewed}),
        "reviewed_count": len(reviewed),
        "unresolved_high_critical": len(unresolved),
    }


def findings_from_report(data):
    return [
        {**v, "Target": section["Target"]}
        for section in data.get("Results", [])
        for v in section.get("Vulnerabilities", [])
        if v["Severity"] in {"HIGH", "CRITICAL"}
    ]
