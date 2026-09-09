"""Synthetic maintenance guards; these tests never start Docker or read real secrets."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import maintenance_testbed as lab  # noqa: E402


class MaintenanceGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        recipe = self.root / "deploy/images/mysql/Dockerfile"
        recipe.parent.mkdir(parents=True)
        recipe.write_text("fixture", encoding="utf-8")
        report = self.evidence / "report.json"
        report.write_text("{}", encoding="utf-8")
        self.record = {
            "name": "mysql",
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "findings": {"HIGH": 0, "CRITICAL": 0},
            "archive": str(self.evidence / "image.tar"),
            "report": str(report),
            "image_id": "fixture",
            "archive_sha256": "fixture",
            "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
            "recipe_hashes": {
                str(recipe.relative_to(self.root)): hashlib.sha256(recipe.read_bytes()).hexdigest()
            },
            "reference": "fixture@sha256:fixture",
        }
        for target, value in (("ROOT", self.root), ("EVIDENCE", self.evidence)):
            context = patch.object(lab, target, value)
            context.start()
            self.addCleanup(context.stop)
        context = patch.object(lab.verify_infra, "SERVICES", {"mysql"})
        context.start()
        self.addCleanup(context.stop)
        context = patch.object(lab, "archive_identity", return_value={"archive_sha256": "fixture"})
        self.archive = context.start()
        self.addCleanup(context.stop)

    def evaluate(self):
        (self.evidence / "mysql-passed.json").write_text(json.dumps(self.record), encoding="utf-8")
        return lab.passed_images()

    def test_fresh_bound_record(self):
        self.assertEqual(self.evaluate(), {"mysql": self.record["reference"]})

    def test_expired_and_future_records_rejected(self):
        for hours in (-25, 1):
            self.record["scanned_at"] = (
                datetime.now(timezone.utc) + timedelta(hours=hours)
            ).isoformat()
            with self.assertRaises(ValueError):
                self.evaluate()

    def test_high_or_critical_rejected(self):
        for severity in ("HIGH", "CRITICAL"):
            self.record["findings"] = {"HIGH": 0, "CRITICAL": 0, severity: 1}
            with self.assertRaises(ValueError):
                self.evaluate()

    def test_evidence_escape_rejected_before_archive_read(self):
        self.record["archive"] = str(self.root / "outside.tar")
        with self.assertRaises(ValueError):
            self.evaluate()
        self.archive.assert_not_called()

    def test_changed_report_rejected(self):
        self.record["report_sha256"] = "changed"
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_changed_recipe_rejected(self):
        for name in self.record["recipe_hashes"]:
            self.record["recipe_hashes"][name] = "changed"
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_recipe_escape_rejected(self):
        self.record["recipe_hashes"] = {"../outside": "changed"}
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_missing_recipe_list_rejected(self):
        self.record["recipe_hashes"] = {}
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_wrong_service_record_rejected(self):
        self.record["name"] = "redis"
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_existing_lab_not_overwritten(self):
        with patch.object(lab, "LAB", self.evidence), patch.object(lab, "passed_images") as scans:
            with self.assertRaises(ValueError):
                lab.prepare()
            scans.assert_not_called()


if __name__ == "__main__":
    unittest.main()
