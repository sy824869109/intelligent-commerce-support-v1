"""Verified-fix review cannot generalize to another artifact, version or vulnerability."""

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
reviews = importlib.import_module("environment_image_review")
services = importlib.import_module("environment_services")


class ImageReviewTests(unittest.TestCase):
    def setUp(self):
        self.rule = json.loads(reviews.REVIEW.read_text())
        self.identity = {
            "image_id": self.rule["image_id"],
            "config_id": self.rule["config_id"],
            "binary_sha256": {self.rule["binary_path"]: self.rule["binary_sha256"]},
        }
        self.findings = [
            {
                "Target": self.rule["binary_path"],
                "PkgName": self.rule["package"],
                "InstalledVersion": self.rule["version"],
                "VulnerabilityID": cve,
                "Severity": "HIGH",
            }
            for cve in sorted(reviews.ALLOWED)
        ]

    def test_exact_upstream_fixed_artifact(self):
        result = reviews.review_findings(self.identity, self.findings)
        self.assertEqual(result["reviewed_count"], 2)
        self.assertEqual(result["unresolved_high_critical"], 0)
        self.assertEqual(len(self.findings), 2)  # Raw input is preserved.

    def test_artifact_identity_changes_revoke_review(self):
        for key in ("image_id", "config_id", "binary_sha256"):
            identity = deepcopy(self.identity)
            identity[key] = {} if key == "binary_sha256" else "sha256:" + "0" * 64
            with self.subTest(key=key):
                result = reviews.review_findings(identity, self.findings)
                self.assertEqual(result["unresolved_high_critical"], 2)

    def test_new_cve_package_version_or_location_never_inherits_review(self):
        for key, replacement in (
            ("VulnerabilityID", "CVE-2099-99999"),
            ("PkgName", "other/package"),
            ("InstalledVersion", "v1.5.0"),
            ("Target", "other/binary"),
        ):
            finding = {**self.findings[0], key: replacement}
            with self.subTest(key=key):
                self.assertEqual(
                    reviews.review_findings(self.identity, [finding])["unresolved_high_critical"], 1
                )

    def test_startup_rechecks_raw_report_and_review(self):
        report = {
            "Metadata": {"ImageID": self.rule["config_id"]},
            "Results": [{"Target": self.rule["binary_path"], "Vulnerabilities": self.findings}],
        }
        raw = json.dumps(report).encode()
        record = {
            **self.identity,
            "high_critical": 2,
            "report_sha256": hashlib.sha256(raw).hexdigest(),
            **reviews.review_findings(self.identity, self.findings),
        }
        audit = {
            "status": "PASS_REVIEWED",
            "checked_at": datetime.now(UTC).isoformat(),
            "images": {"grafana": record},
        }
        locked = {"grafana": {"image_id": self.rule["image_id"]}}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "image-audit").mkdir()
            report_path = folder / "image-audit/grafana.json"
            report_path.write_bytes(raw)
            with patch.object(services, "LOCAL", folder):
                services.validate_audit(locked, audit)
                for field, changed in (
                    ("image_id", "wrong"),
                    ("high_critical", 0),
                    ("review_sha256", "wrong"),
                ):
                    bad = deepcopy(audit)
                    bad["images"]["grafana"][field] = changed
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        services.validate_audit(locked, bad)
                report_path.write_bytes(raw + b" ")
                with self.assertRaises(ValueError):
                    services.validate_audit(locked, audit)

    def test_missing_service_or_old_audit_rejected(self):
        for audit in (
            {"status": "PASS", "checked_at": "2020-01-01T00:00:00+00:00", "images": {}},
            {"status": "PASS", "checked_at": datetime.now(UTC).isoformat(), "images": {}},
        ):
            with self.assertRaises(ValueError):
                services.validate_audit({"grafana": {}}, audit)


if __name__ == "__main__":
    unittest.main()
