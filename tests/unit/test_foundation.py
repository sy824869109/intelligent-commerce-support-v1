"""M00.4 tooling tests, not AT-* business tests; fixtures are synthetic."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

# Standalone unittest discovery requires the repository tooling path above.
import verify_ci as ci  # noqa: E402
import verify_governance as governance  # noqa: E402
import verify_implementation_standards as standards  # noqa: E402
import verify_structure as structure  # noqa: E402


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = ci.parse_workflow(
            (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        )
        self.stages = json.loads((ROOT / ".github/ci-stages.json").read_text(encoding="utf-8"))

    def validate(self):
        return ci.validate_workflow(self.workflow, self.stages, ROOT)

    def test_real_workflow(self):
        self.assertEqual([], self.validate())

    def test_yaml_on_is_not_boolean(self):
        self.assertIn("on", self.workflow)
        self.assertNotIn(True, self.workflow)

    def test_duplicate_yaml_keys_rejected(self):
        with self.assertRaises(ValueError):
            ci.parse_workflow("name: a\nname: b\n")

    def test_privileged_trigger_rejected(self):
        self.workflow["on"]["pull_request_target"] = {}
        self.assertTrue(self.validate())

    def test_write_permissions_rejected(self):
        self.workflow["permissions"] = {"contents": "write"}
        self.assertTrue(self.validate())

    def test_floating_action_rejected(self):
        self.workflow["jobs"]["foundation"]["steps"][0]["uses"] = "actions/checkout@v6"
        self.assertTrue(self.validate())

    def test_persisted_credentials_rejected(self):
        self.workflow["jobs"]["foundation"]["steps"][0]["with"]["persist-credentials"] = "true"
        self.assertTrue(self.validate())

    def test_silent_failure_rejected(self):
        self.workflow["jobs"]["foundation"]["steps"][-1]["continue-on-error"] = "true"
        self.assertTrue(self.validate())

    def test_conditional_foundation_rejected(self):
        self.workflow["jobs"]["foundation"]["if"] = "${{ false }}"
        self.assertTrue(self.validate())

    def test_fake_enabled_placeholder_rejected(self):
        self.workflow["jobs"]["backend"]["steps"][-1]["run"] = 'echo "passed"'
        self.assertTrue(self.validate())

    def test_new_runtime_source_requires_activation(self):
        self.stages["stages"]["backend"]["state"] = "NOT_IMPLEMENTED"
        self.stages["stages"]["security-audit"]["state"] = "NOT_IMPLEMENTED"
        with tempfile.TemporaryDirectory(prefix="commerce-ci-test-") as folder:
            root = Path(folder)
            target = root / "apps" / "api-gateway"
            target.mkdir(parents=True)
            (target / "main.py").write_text("# Synthetic runtime marker\n", encoding="utf-8")
            errors = ci.validate_workflow(self.workflow, self.stages, root)
            self.assertTrue(any("activate real backend" in error for error in errors))
            self.assertTrue(any("activate real security-audit" in error for error in errors))

    def test_missing_stage_rejected(self):
        del self.stages["stages"]["frontend"]
        self.assertTrue(self.validate())

    def test_missing_real_runner_rejected(self):
        self.workflow["jobs"]["foundation"]["steps"][-1]["run"] = 'echo "passed"'
        self.assertTrue(self.validate())

    def test_timeout_required(self):
        self.workflow["jobs"]["foundation"]["timeout-minutes"] = "0"
        self.assertTrue(self.validate())

    def test_hash_install_cannot_be_disabled(self):
        self.workflow["jobs"]["foundation"]["steps"][3]["run"] = "python -m pip install ruff"
        self.assertTrue(self.validate())

    def test_real_step_cannot_be_skipped(self):
        self.workflow["jobs"]["foundation"]["steps"][-1]["if"] = "${{ false }}"
        self.assertTrue(self.validate())


class AssetSafetyTests(unittest.TestCase):
    def test_reference_archives_rejected(self):
        self.assertIn("forbidden-asset", ci.asset_findings("references/original.zip", b"fixture"))

    def test_local_environment_rejected(self):
        self.assertIn("private-environment", ci.asset_findings(".env.production", b"fixture"))

    def test_example_environment_allowed(self):
        self.assertEqual([], ci.asset_findings(".env.example", b"PASSWORD=replace-me"))

    def test_model_rejected(self):
        self.assertIn("forbidden-asset", ci.asset_findings("weights.gguf", b"fixture"))

    def test_synthetic_token_redacted(self):
        fixture = ("gh" + "p_" + "A" * 36).encode()
        reasons = ci.asset_findings("example.txt", fixture)
        self.assertEqual(["possible-secret"], reasons)
        self.assertNotIn(fixture.decode(), str(reasons))

    def test_private_key_detected(self):
        fixture = b"-----BEGIN " + b"PRIVATE KEY-----"
        self.assertIn("possible-secret", ci.asset_findings("example.txt", fixture))

    def test_large_file_rejected(self):
        self.assertIn(
            "oversized-tracked-asset", ci.asset_findings("large.dat", b"0" * (10 * 1024 * 1024 + 1))
        )

    def test_diagram_allowed(self):
        self.assertEqual([], ci.asset_findings("docs/diagram.png", b"synthetic-small-image"))


class DocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = standards.load_documents(ROOT)

    def validate_changed(self, key, change):
        documents = copy.deepcopy(self.documents)
        documents[key] = change(documents[key])
        return standards.validate_documents(ROOT, documents)[0]

    def test_standards_baseline(self):
        errors, counts = standards.validate_documents(ROOT, self.documents)
        self.assertEqual([], errors)
        self.assertEqual({"rules": 48, "acceptance_cases": 93, "json_examples": 5}, counts)

    def test_undefined_rule(self):
        key = standards.STANDARD_DIR / "README.md"
        self.assertTrue(self.validate_changed(key, lambda text: text + "\nC-99\n"))

    def test_broken_link(self):
        key = standards.STANDARD_DIR / "README.md"
        self.assertTrue(
            self.validate_changed(key, lambda text: text + "\n[missing](never-present.md)\n")
        )

    def test_invalid_json(self):
        key = standards.STANDARD_DIR / standards.STANDARD_FILES["E"]
        self.assertTrue(
            self.validate_changed(key, lambda text: text.replace('"REQ001"', '"REQ001",', 1))
        )

    def test_duplicate_case(self):
        key = standards.STANDARD_DIR / standards.STANDARD_FILES["A"]
        self.assertTrue(self.validate_changed(key, lambda text: text.replace("AT-C13", "AT-C12")))

    def test_scope_gap(self):
        key = standards.STANDARD_DIR / "业务范围与验收映射.md"
        self.assertTrue(self.validate_changed(key, lambda text: text.replace("BS-09", "BS-08")))

    def test_unknown_acceptance_reference(self):
        key = standards.STANDARD_DIR / "业务范围与验收映射.md"
        self.assertTrue(self.validate_changed(key, lambda text: text + "\nAT-B99\n"))

    def test_structure_present(self):
        self.assertEqual([], structure.find_missing(ROOT))

    def test_empty_structure_fails(self):
        with tempfile.TemporaryDirectory(prefix="commerce-structure-test-") as folder:
            self.assertTrue(structure.find_missing(Path(folder)))

    def test_version_is_valid(self):
        self.assertIsNotNone(governance.SEMVER_PATTERN.fullmatch("0.1.0-dev.0"))
        self.assertIsNone(governance.SEMVER_PATTERN.fullmatch("latest"))


if __name__ == "__main__":
    unittest.main()
