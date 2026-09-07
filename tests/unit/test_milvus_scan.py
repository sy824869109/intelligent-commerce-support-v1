"""Milvus 扫描候选门禁：合成报告测试不代表真实镜像已通过。"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import milvus_scan as gate  # noqa: E402
from test_storage_image import (  # noqa: E402
    CONFIG_ID,
    FIXTURE_MEMBERS,
    IMAGE_ID,
    write_archive,
)


def clean_report():
    return {
        "SchemaVersion": 2,
        "ArtifactType": "container_image",
        "Metadata": {"ImageID": CONFIG_ID},
        "Results": [
            {"Target": "fixture (ubuntu 22.04)", "Class": "os-pkgs", "Type": "ubuntu"},
            *[
                {"Target": name, "Class": "lang-pkgs", "Type": "gobinary"}
                for name in sorted(gate.REQUIRED_GO_TARGETS)
            ],
        ],
    }


class MilvusScanTests(unittest.TestCase):
    def test_complete_clean_report(self):
        self.assertEqual(sum(gate.scan_findings(clean_report()).values()), 0)

    def test_each_required_target_is_mandatory(self):
        for index in range(3):
            with self.subTest(index=index):
                report = clean_report()
                del report["Results"][index]
                with self.assertRaises(gate.ImageGateError):
                    gate.scan_findings(report)

    def test_wrong_os_rejected(self):
        report = clean_report()
        report["Results"][0]["Type"] = "alpine"
        with self.assertRaises(gate.ImageGateError):
            gate.scan_findings(report)

    def test_unrelated_binary_cannot_replace_parser(self):
        report = clean_report()
        report["Results"][2]["Target"] = "tmp/other-go-binary"
        with self.assertRaises(gate.ImageGateError):
            gate.scan_findings(report)

    def test_high_and_critical_in_every_target_rejected(self):
        for index in range(3):
            for severity in ("HIGH", "CRITICAL"):
                with self.subTest(index=index, severity=severity):
                    report = clean_report()
                    report["Results"][index]["Vulnerabilities"] = [{"Severity": severity}]
                    with self.assertRaises(gate.ImageGateError):
                        gate.scan_findings(report)

    def test_additional_target_findings_also_block(self):
        report = clean_report()
        report["Results"].append(
            {
                "Target": "other",
                "Class": "lang-pkgs",
                "Type": "gobinary",
                "Vulnerabilities": [{"Severity": "HIGH"}],
            }
        )
        with self.assertRaises(gate.ImageGateError):
            gate.scan_findings(report)

    def test_lower_severities_preserved(self):
        report = clean_report()
        report["Results"][1]["Vulnerabilities"] = [
            {"Severity": value} for value in ("LOW", "MEDIUM", "UNKNOWN")
        ] + [{}]
        counts = gate.scan_findings(report)
        self.assertEqual((counts["LOW"], counts["MEDIUM"], counts["UNKNOWN"]), (1, 1, 2))

    def test_malformed_report_rejected(self):
        for report in (
            None,
            [],
            {},
            {**clean_report(), "Results": []},
            {**clean_report(), "SchemaVersion": 1},
        ):
            with self.subTest(report=report), self.assertRaises(gate.ImageGateError):
                gate.scan_findings(report)

    def test_malformed_target_rejected(self):
        for target in (
            None,
            [],
            {},
            {"Target": [], "Class": "os-pkgs", "Type": "ubuntu"},
        ):
            report = clean_report()
            report["Results"].append(target)
            with self.subTest(target=target), self.assertRaises(gate.ImageGateError):
                gate.scan_findings(report)

    def test_malformed_findings_rejected(self):
        for findings in (
            {},
            "",
            False,
            [None],
            [{"Severity": []}],
            [{"Severity": "high"}],
        ):
            report = clean_report()
            report["Results"][0]["Vulnerabilities"] = findings
            with (
                self.subTest(findings=findings),
                self.assertRaises(gate.ImageGateError),
            ):
                gate.scan_findings(report)

    def test_duplicate_target_rejected(self):
        report = clean_report()
        report["Results"].append(copy.deepcopy(report["Results"][1]))
        with self.assertRaises(gate.ImageGateError):
            gate.scan_findings(report)

    def test_null_findings_are_valid(self):
        report = clean_report()
        report["Results"][0]["Vulnerabilities"] = None
        self.assertEqual(gate.scan_findings(report)["HIGH"], 0)

    def test_archive_bound_report_is_not_compose_admission(self):
        with tempfile.TemporaryDirectory(prefix="ics-milvus-scan-test-") as directory:
            folder = Path(directory)
            archive, report = folder / "image.tar", folder / "scan.json"
            write_archive(archive, FIXTURE_MEMBERS)
            report.write_text(json.dumps(clean_report()), encoding="utf-8")
            result = gate.verify_report(archive, report, IMAGE_ID)
            self.assertEqual(result["config_id"], CONFIG_ID)
            self.assertFalse(result["compose_admitted"])
            parsed = clean_report()
            parsed["Metadata"]["ImageID"] = "sha256:" + "0" * 64
            report.write_text(json.dumps(parsed), encoding="utf-8")
            with self.assertRaises(gate.ImageGateError):
                gate.verify_report(archive, report, IMAGE_ID)

    def test_cli_invalid_input_fails(self):
        with patch.object(
            sys,
            "argv",
            [
                "milvus_scan",
                "--archive",
                "missing.tar",
                "--report",
                "missing.json",
                "--image-id",
                "bad",
            ],
        ):
            self.assertEqual(gate.main(), 1)


if __name__ == "__main__":
    unittest.main()
