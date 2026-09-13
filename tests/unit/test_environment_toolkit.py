"""Environment-only guards: no Docker, downloads, model imports or real credentials."""

from pathlib import Path
import sys
import importlib
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
services = importlib.import_module("environment_services")
models = importlib.import_module("prepare_local_models")
checks = importlib.import_module("check_environment")


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

    def cloud_fixture(self, url="https://dashscope.aliyuncs.com/compatible-mode/v1"):
        # Obviously synthetic unit-test marker, never a provider credential.
        return {
            "LLM_BASE_URL": url,
            "LLM_API_KEY": "apiKey-sk-ws-UNIT_TEST_ONLY",
            "LLM_MODEL": "test-model",
        }

    def test_cloud_probe_no_redirect_no_proxy_small_request(self):
        mock_client = MagicMock()
        client = mock_client.return_value.__enter__.return_value
        client.post.return_value.status_code = 200
        client.post.return_value.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.env").touch()
            with (
                patch.object(checks, "LOCAL", root),
                patch.dict(
                    sys.modules,
                    {
                        "dotenv": SimpleNamespace(
                            dotenv_values=lambda *a, **k: self.cloud_fixture()
                        ),
                        "httpx": SimpleNamespace(Client=mock_client),
                    },
                ),
            ):
                result = checks.cloud_config(live=True)
        self.assertEqual(result["live_call"], "PASS")
        self.assertTrue(result["ui_label_removed"])
        mock_client.assert_called_once_with(timeout=30, follow_redirects=False, trust_env=False)
        sent = client.post.call_args.kwargs
        self.assertEqual(sent["json"]["max_tokens"], 8)
        self.assertEqual(sent["headers"]["Authorization"], "Bearer sk-ws-UNIT_TEST_ONLY")

    def test_cloud_rejects_unreviewed_host_before_sending(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.env").touch()
            with (
                patch.object(checks, "LOCAL", root),
                patch.dict(
                    sys.modules,
                    {
                        "dotenv": SimpleNamespace(
                            dotenv_values=lambda *a, **k: self.cloud_fixture(
                                "https://unreviewed.invalid/compatible-mode/v1"
                            )
                        )
                    },
                ),
            ):
                with self.assertRaises(ValueError):
                    checks.cloud_config(live=True)

    def test_cloud_configuration_does_not_make_implicit_paid_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.env").touch()
            with (
                patch.object(checks, "LOCAL", root),
                patch.dict(
                    sys.modules,
                    {"dotenv": SimpleNamespace(dotenv_values=lambda *a, **k: self.cloud_fixture())},
                ),
            ):
                result = checks.cloud_config()
        self.assertEqual(result["live_call"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
