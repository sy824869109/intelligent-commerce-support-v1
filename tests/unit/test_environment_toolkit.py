"""Environment-only guards: no Docker, downloads, model imports or real credentials."""

from pathlib import Path
import sys
import importlib
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
services = importlib.import_module("environment_services")
models = importlib.import_module("prepare_local_models")


class EnvironmentToolkitTests(unittest.TestCase):
    def test_model_scope_and_revisions_are_fixed(self):
        self.assertEqual(set(models.MODELS), {"bge-m3", "bge-reranker-v2-m3"})
        for repo, revision, license_name in models.MODELS.values():
            self.assertTrue(repo.startswith("BAAI/"))
            self.assertEqual(len(revision), 40)
            self.assertIn(license_name, {"mit", "apache-2.0"})

    def test_model_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            models.safe_target(ROOT / "_local_artifacts/models/bge-m3", "../../../../escape.bin")

    def test_known_model_path_accepted(self):
        base = ROOT / "_local_artifacts/models/bge-m3"
        self.assertEqual(
            models.safe_target(base, "1_Pooling/config.json"), base / "1_Pooling/config.json"
        )

    def test_tooling_manifest_only_loopback_no_privilege(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(services, "LOCAL", Path(temporary)):
                images = {
                    name: {"reference": "example@sha256:" + "0" * 64} for name in services.TAGS
                }
                config = services.compose_config(images)
        self.assertEqual(config["name"], "ics-v1-tools")
        self.assertEqual(len(config["services"]), 6)
        for item in config["services"].values():
            self.assertEqual(item["cap_drop"], ["ALL"])
            self.assertTrue(item["read_only"])
            for port in item.get("ports", []):
                self.assertTrue(port.startswith("127.0.0.1:"))
            for mount in item.get("volumes", []):
                self.assertNotIn("docker.sock", mount["source"])

    def test_escape_tooling_data_rejected(self):
        with self.assertRaises(ValueError):
            services.owned_path(services.LOCAL / "../../../../../outside")

    def test_no_new_conda_environment_in_setup(self):
        setup = (ROOT / "scripts/setup_v1_environment.ps1").read_text(encoding="utf-8")
        self.assertNotIn("conda.exe create", setup)
        self.assertIn("--require-hashes", setup)
        terminal = (ROOT / "scripts/enter_environment.ps1").read_text(encoding="utf-8")
        self.assertIn("envs/intelligent-commerce-support-v1", terminal)

    def test_frontend_is_vue3_environment_only(self):
        import json

        config = json.loads((ROOT / "deploy/dev-environment/frontend/package.json").read_text())
        self.assertTrue(config["private"])
        self.assertTrue(config["dependencies"]["vue"].startswith("3."))
        self.assertNotIn("react", config["dependencies"])


if __name__ == "__main__":
    unittest.main()
