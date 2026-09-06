"""M01.1 配置和安全边界测试；不启动 Docker，也不冒充业务验收。"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import local_infra as runtime  # noqa: E402
import verify_infra as infra  # noqa: E402


class ComposeTests(unittest.TestCase):
    def setUp(self):
        folder = ROOT / "deploy/compose"
        self.config = infra.parse_compose(
            (folder / "infra.compose.yml").read_text(encoding="utf-8")
        )
        self.lock = json.loads((folder / "images.lock.json").read_text(encoding="utf-8"))

    def validate(self):
        return infra.validate_compose(self.config, self.lock)

    def test_real_config(self):
        self.assertEqual([], self.validate())

    def test_duplicate_key_rejected(self):
        with self.assertRaises(ValueError):
            infra.parse_compose("services: {}\nservices: {}\n")

    def test_merge_does_not_hide_duplicate(self):
        with self.assertRaises(ValueError):
            infra.parse_compose("x: &a {restart: always}\ny:\n  <<: *a\n  ports: []\n  ports: []\n")

    def test_latest_rejected(self):
        self.config["services"]["redis"]["image"] = "redis:latest"
        self.assertTrue(self.validate())

    def test_lock_mismatch_rejected(self):
        self.lock["images"]["mysql"] = "mysql:8.4.11@sha256:" + "0" * 64
        self.assertTrue(self.validate())

    def test_disabled_profile_is_not_security_boundary(self):
        self.config["services"]["minio"] = {"image": "minio/minio:latest", "profiles": ["disabled"]}
        self.assertTrue(self.validate())

    def test_wildcard_port_rejected(self):
        self.config["services"]["mysql"]["ports"] = ["0.0.0.0:23306:3306"]
        self.assertTrue(self.validate())

    def test_etcd_host_port_rejected(self):
        self.config["services"]["etcd"]["ports"] = ["127.0.0.1:2379:2379"]
        self.assertTrue(self.validate())

    def test_host_path_rejected(self):
        self.config["services"]["mysql"]["volumes"] = ["F:/old/data:/var/lib/mysql"]
        self.assertTrue(self.validate())

    def test_external_volume_rejected(self):
        self.config["volumes"]["mysql_data"] = {"external": True, "name": "knowforge-mysql"}
        self.assertTrue(self.validate())

    def test_external_network_rejected(self):
        self.config["networks"] = {"infra": {"external": True}}
        self.assertTrue(self.validate())

    def test_privileged_rejected(self):
        self.config["services"]["redis"]["privileged"] = True
        self.assertTrue(self.validate())

    def test_plain_password_rejected(self):
        self.config["services"]["mysql"]["environment"]["MYSQL_ROOT_PASSWORD"] = "synthetic"
        self.assertTrue(self.validate())

    def test_healthcheck_removed_rejected(self):
        del self.config["services"]["etcd"]["healthcheck"]
        self.assertTrue(self.validate())

    def test_healthcheck_disabled_rejected(self):
        self.config["services"]["redis"]["healthcheck"]["disable"] = True
        self.assertTrue(self.validate())

    def test_redis_without_generated_auth_rejected(self):
        self.config["services"]["redis"]["command"] = ["redis-server"]
        self.assertTrue(self.validate())

    def test_secret_outside_project_rejected(self):
        self.config["secrets"]["redis_config"]["file"] = "../../old/redis.conf"
        self.assertTrue(self.validate())

    def test_include_override_rejected(self):
        self.config["include"] = ["old.yml"]
        self.assertTrue(self.validate())

    def test_mysql_skip_grants_rejected(self):
        self.config["services"]["mysql"]["command"] = ["--skip-grant-tables"]
        self.assertTrue(self.validate())

    def test_fake_health_rejected(self):
        self.config["services"]["redis"]["healthcheck"]["test"] = ["CMD", "true"]
        self.assertTrue(self.validate())

    def test_unbounded_logs_rejected(self):
        self.config["services"]["mysql"]["logging"].pop("options")
        self.assertTrue(self.validate())

    def test_missing_instance_label_rejected(self):
        self.config["volumes"]["mysql_data"] = {}
        self.assertTrue(self.validate())

    def test_etcd_local_bridge_rejected(self):
        self.config["services"]["etcd"]["networks"] = ["infra", "local"]
        self.assertTrue(self.validate())


class LocalCredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ics-infra-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "deploy/compose"
        self.folder.mkdir(parents=True)
        self.template = (
            "MYSQL_DATABASE=ics_dev\nMYSQL_USER=ics_dev\nMYSQL_PORT=23306\nREDIS_PORT=26379\n"
            "INFRA_INSTANCE_ID=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        )
        (self.folder / ".env.example").write_text(self.template, encoding="utf-8")

    def initialize(self):
        with patch("builtins.print") as printer:
            runtime.initialize(self.root)
        return printer

    def test_initialize_and_validate(self):
        printer = self.initialize()
        result = runtime.validate_local_files(self.root)
        self.assertEqual("ics_dev", result["MYSQL_USER"])
        for path in (self.folder / "secrets").iterdir():
            self.assertNotIn(path.read_text(encoding="utf-8").strip(), str(printer.call_args_list))

    def test_existing_credentials_never_overwritten(self):
        self.initialize()
        old = {p.name: p.read_bytes() for p in (self.folder / "secrets").iterdir()}
        with self.assertRaises(runtime.InfraError):
            runtime.initialize(self.root)
        self.assertEqual(old, {p.name: p.read_bytes() for p in (self.folder / "secrets").iterdir()})

    def test_partial_configuration_refused(self):
        (self.folder / "secrets").mkdir()
        with self.assertRaises(runtime.InfraError):
            runtime.initialize(self.root)

    def test_placeholder_secret_refused(self):
        self.initialize()
        (self.folder / "secrets/mysql_password").write_text("replace_me", encoding="utf-8")
        with self.assertRaises(runtime.InfraError):
            runtime.validate_local_files(self.root)

    def test_redis_no_auth_change_refused(self):
        self.initialize()
        (self.folder / "secrets/redis_config").write_text("protected-mode no\n", encoding="utf-8")
        with self.assertRaises(runtime.InfraError):
            runtime.validate_local_files(self.root)

    def test_duplicate_env_refused(self):
        with self.assertRaises(runtime.InfraError):
            runtime.parse_env(self.template + "MYSQL_PORT=23307\n")

    def test_root_user_refused(self):
        with self.assertRaises(runtime.InfraError):
            runtime.parse_env(self.template.replace("MYSQL_USER=ics_dev", "MYSQL_USER=root"))

    def test_invalid_port_refused(self):
        with self.assertRaises(runtime.InfraError):
            runtime.parse_env(self.template.replace("23306", "0"))

    def test_duplicate_port_refused(self):
        with self.assertRaises(runtime.InfraError):
            runtime.parse_env(self.template.replace("26379", "23306"))

    def test_compose_overrides_refused(self):
        for key in (
            "COMPOSE_FILE",
            "COMPOSE_PROFILES",
            "COMPOSE_PROJECT_NAME",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
        ):
            with self.subTest(key=key), self.assertRaises(runtime.InfraError):
                runtime.compose_environment({key: "synthetic"})

    def test_shell_does_not_override_env_file(self):
        result = runtime.compose_environment({"MYSQL_PORT": "3306", "PATH": "synthetic"})
        self.assertEqual({"PATH": "synthetic"}, result)

    def test_fixed_compose_arguments(self):
        arguments = runtime.compose_prefix(["docker", "--context", "desktop-linux"], self.root)
        self.assertIn("ics-v1-dev", arguments)
        self.assertIn(str(self.folder / "infra.compose.yml"), arguments)
        self.assertNotIn("down", arguments)
        self.assertNotIn("--volumes", arguments)

    def test_validation_does_not_mutate_config(self):
        self.initialize()
        before = copy.deepcopy((self.folder / ".env").read_bytes())
        runtime.validate_local_files(self.root)
        self.assertEqual(before, (self.folder / ".env").read_bytes())

    def test_template_generates_unique_instance(self):
        (self.folder / ".env.example").write_text(
            self.template.replace("a" * 32, "generated_on_init"), encoding="utf-8"
        )
        self.initialize()
        result = runtime.validate_local_files(self.root)
        self.assertRegex(result["INFRA_INSTANCE_ID"], r"^[a-f0-9]{32}$")
        self.assertNotEqual("a" * 32, result["INFRA_INSTANCE_ID"])


class OwnershipTests(unittest.TestCase):
    @staticmethod
    def completed(output):
        return subprocess.CompletedProcess([], 0, stdout=output, stderr="")

    def test_remote_pipe_rejected(self):
        self.assertFalse(runtime.local_endpoint("npipe:////other-host/pipe/docker_engine"))
        self.assertFalse(runtime.local_endpoint("tcp://127.0.0.1:2375"))
        self.assertFalse(runtime.local_endpoint("ssh://remote"))
        self.assertTrue(runtime.local_endpoint("npipe:////./pipe/dockerDesktopLinuxEngine"))
        self.assertTrue(runtime.local_endpoint("unix:///var/run/docker.sock"))

    def test_unknown_orphan_volume_rejected(self):
        with patch.object(
            runtime,
            "invoke",
            side_effect=[self.completed("ics-v1-dev_mysql_data\n"), self.completed("{}")],
        ):
            with self.assertRaises(runtime.InfraError):
                runtime.check_resources(["docker"], {}, "a" * 32)

    def test_owned_orphan_volume_allowed(self):
        labels = json.dumps(
            {"org.ics.instance": "a" * 32, "com.docker.compose.project": "ics-v1-dev"}
        )
        with patch.object(
            runtime,
            "invoke",
            side_effect=[
                self.completed("ics-v1-dev_mysql_data\n"),
                self.completed(labels),
                self.completed(""),
            ],
        ):
            runtime.check_resources(["docker"], {}, "a" * 32)

    def test_unknown_network_rejected(self):
        with patch.object(
            runtime,
            "invoke",
            side_effect=[
                self.completed(""),
                self.completed("ics-v1-dev_infra\n"),
                self.completed("{}"),
            ],
        ):
            with self.assertRaises(runtime.InfraError):
                runtime.check_resources(["docker"], {}, "a" * 32)

    def test_stop_refuses_other_directory(self):
        labels = json.dumps({"com.docker.compose.project.working_dir": str(ROOT / "different")})
        with patch.object(
            runtime,
            "invoke",
            side_effect=[self.completed("synthetic-id\n"), self.completed(labels)],
        ) as call:
            with self.assertRaises(runtime.InfraError):
                runtime.stop_owned(["docker"], {})
            self.assertFalse(any("stop" in item.args[0] for item in call.call_args_list))

    def test_stop_owned_without_secrets_and_keeps_volumes(self):
        labels = json.dumps(
            {
                "com.docker.compose.project.working_dir": str(runtime.ROOT / "deploy/compose"),
                "com.docker.compose.service": "mysql",
                "org.ics.instance": "a" * 32,
            }
        )
        with (
            patch.object(
                runtime,
                "invoke",
                side_effect=[
                    self.completed("synthetic-id\n"),
                    self.completed(labels),
                    self.completed(""),
                ],
            ) as call,
            patch("builtins.print"),
        ):
            runtime.stop_owned(["docker"], {})
            self.assertEqual(
                ["docker", "stop", "--time", "30", "synthetic-id"], call.call_args.args[0]
            )
            self.assertFalse(any("volume" in item.args[0] for item in call.call_args_list))


class HostProbeTests(unittest.TestCase):
    def test_protocol_probe_success(self):
        mysql = MagicMock()
        mysql.__enter__.return_value.recv.return_value = b"\x20\x00\x00\x00\x0a8.4.11\x00"
        redis = MagicMock()
        redis.__enter__.return_value.recv.return_value = b"-NOAUTH Authentication required.\r\n"
        with (
            patch.object(runtime.socket, "create_connection", side_effect=[mysql, redis]),
            patch("builtins.print"),
        ):
            runtime.host_probe({"MYSQL_PORT": "23306", "REDIS_PORT": "26379"})

    def test_wrong_service_on_host_port_refused(self):
        connection = MagicMock()
        connection.__enter__.return_value.recv.return_value = b"HTTP/1.1 200 OK"
        with patch.object(runtime.socket, "create_connection", return_value=connection):
            with self.assertRaises(runtime.InfraError):
                runtime.host_probe({"MYSQL_PORT": "23306", "REDIS_PORT": "26379"})


if __name__ == "__main__":
    unittest.main()
