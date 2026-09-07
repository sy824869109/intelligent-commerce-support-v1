"""M01 本地镜像门禁负测试；只使用临时构建配方/合成 JSON，不调用 Docker。"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import storage_image as gate  # noqa: E402


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def oci_fixture():
    """Small content-addressed OCI graph; no Docker daemon or downloaded artifacts."""
    blobs = {}

    def blob(data, media_type):
        identifier = digest(data)
        blobs["blobs/sha256/" + identifier.split(":")[1]] = data
        return {"mediaType": media_type, "digest": identifier, "size": len(data)}

    layer = blob(b"synthetic uncompressed layer bytes", "application/vnd.oci.image.layer.v1.tar")
    config = blob(
        json_bytes(
            {
                "os": "linux",
                "architecture": "amd64",
                "rootfs": {"type": "layers", "diff_ids": [layer["digest"]]},
            }
        ),
        "application/vnd.oci.image.config.v1+json",
    )
    media_type = "application/vnd.oci.image.manifest.v1+json"
    manifest = blob(
        json_bytes(
            {
                "schemaVersion": 2,
                "mediaType": media_type,
                "config": config,
                "layers": [layer],
            }
        ),
        media_type,
    )
    blobs["index.json"] = json_bytes(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [manifest],
        }
    )
    blobs["oci-layout"] = json_bytes({"imageLayoutVersion": "1.0.0"})
    blobs["manifest.json"] = json_bytes(
        [
            {
                "Config": "blobs/sha256/" + config["digest"].split(":")[1],
                "Layers": ["blobs/sha256/" + layer["digest"].split(":")[1]],
                "RepoTags": [gate.TAG],
            }
        ]
    )
    return blobs, manifest["digest"], config["digest"]


def write_archive(path, members):
    with tarfile.open(path, "w") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


FIXTURE_MEMBERS, IMAGE_ID, CONFIG_ID = oci_fixture()
NOW = datetime(2026, 9, 7, 1, 0, tzinfo=UTC)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)


class StorageImageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ics-image-gate-test-")
        self.addCleanup(temporary.cleanup)
        self.sandbox = Path(temporary.name)
        self.root = self.sandbox / "project"
        self.outside = self.sandbox / "outside"
        self.outside.mkdir()
        self.recipe = self.root / gate.RECIPE
        self.recipe.mkdir(parents=True)
        (self.recipe / "Dockerfile").write_text(
            "FROM scratch\n# synthetic recipe\n", encoding="utf-8"
        )
        (self.recipe / "version.txt").write_text("synthetic-version\n", encoding="utf-8")
        self.report_path = (
            self.root / "data/m01-reports" / ("seaweed-security-" + "b2" * 16 + ".json")
        )
        self.report_path.parent.mkdir(parents=True)
        self.archive_path = self.report_path.with_suffix(".tar")
        write_archive(self.archive_path, FIXTURE_MEMBERS)
        self.report = {
            "SchemaVersion": 2,
            "ArtifactName": gate.TAG,
            "ArtifactType": "container_image",
            "Metadata": {
                "ImageID": CONFIG_ID,
                "OS": {"Family": "alpine", "Name": "3.24.1"},
            },
            "Results": [
                {
                    "Target": "Alpine (synthetic)",
                    "Class": "os-pkgs",
                    "Type": "alpine",
                    "Vulnerabilities": [],
                },
                {
                    "Target": "usr/bin/weed",
                    "Class": "lang-pkgs",
                    "Type": "gobinary",
                    "Vulnerabilities": [],
                },
            ],
        }
        self.write_report()
        self.record = {
            "schema_version": gate.RECORD_VERSION,
            "tag": gate.TAG,
            "image_id": IMAGE_ID,
            "config_id": CONFIG_ID,
            "archive": self.archive_path.relative_to(self.root).as_posix(),
            "archive_sha256": hashlib.sha256(self.archive_path.read_bytes()).hexdigest(),
            "recipe_sha256": gate.recipe_hash(self.root),
            "scanner": gate.SCANNER,
            "scanned_at": NOW.isoformat(),
            "report": self.report_path.relative_to(self.root).as_posix(),
            "report_sha256": hashlib.sha256(self.report_path.read_bytes()).hexdigest(),
            "findings": {},
        }
        self.clock = patch.object(gate, "datetime", FrozenDatetime)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        # Each mutation test starts from evidence accepted by the real validator.
        gate.validate_record(self.root, self.record, IMAGE_ID)

    def write_report(self):
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")

    def rehash_report(self):
        self.write_report()
        self.record["report_sha256"] = hashlib.sha256(self.report_path.read_bytes()).hexdigest()

    def reject(self):
        with self.assertRaises(gate.ImageGateError):
            gate.validate_record(self.root, self.record, IMAGE_ID)

    def symlink(self, link, target, *, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest(
                "Host does not allow creation of test symlinks; Linux CI must cover this case"
            )

    def test_valid_gate_evidence(self):
        gate.validate_record(self.root, self.record, IMAGE_ID)

    def test_seven_day_expiry_boundary(self):
        self.record["scanned_at"] = (NOW - timedelta(days=7)).isoformat()
        gate.validate_record(self.root, self.record, IMAGE_ID)
        self.record["scanned_at"] = (NOW - timedelta(days=7, seconds=1)).isoformat()
        self.reject()

    def test_future_scan_timestamp_rejected(self):
        self.record["scanned_at"] = (NOW + timedelta(seconds=1)).isoformat()
        self.reject()

    def test_malformed_scan_timestamp_safe_rejection(self):
        self.record["scanned_at"] = "synthetic-private-not-a-timestamp"
        self.reject()

    def test_naive_timestamp_rejected(self):
        self.record["scanned_at"] = NOW.replace(tzinfo=None).isoformat()
        self.reject()

    def test_schema_tag_scanner_recipe_identity_mutations(self):
        for key, value in (
            ("schema_version", 1),
            ("tag", "unreviewed:latest"),
            ("scanner", "aquasec/trivy:latest"),
            ("image_id", "sha256:" + "c3" * 32),
            ("recipe_sha256", "0" * 64),
        ):
            with self.subTest(field=key):
                mutated = dict(self.record, **{key: value})
                with self.assertRaises(gate.ImageGateError):
                    gate.validate_record(self.root, mutated, IMAGE_ID)

    def test_actual_image_id_must_be_complete_digest(self):
        for current in ("a1" * 32, "sha256:abc", "sha256:" + "A" * 64):
            with (
                self.subTest(kind=current[:12]),
                self.assertRaises(gate.ImageGateError),
            ):
                gate.validate_record(self.root, dict(self.record, image_id=current), current)

    def test_recipe_content_change_invalidates_lock(self):
        (self.recipe / "Dockerfile").write_text("FROM scratch\n# changed\n", encoding="utf-8")
        self.reject()

    def test_recipe_file_name_change_invalidates_hash(self):
        previous = gate.recipe_hash(self.root)
        (self.recipe / "version.txt").rename(self.recipe / "other-version.txt")
        self.assertNotEqual(previous, gate.recipe_hash(self.root))

    def test_missing_recipe_dockerfile_rejected(self):
        (self.recipe / "Dockerfile").unlink()
        with self.assertRaises(gate.ImageGateError):
            gate.recipe_hash(self.root)

    def test_recipe_root_symlink_escape_rejected(self):
        target = self.outside / "recipe"
        self.recipe.rename(target)
        self.symlink(self.recipe, target, directory=True)
        with self.assertRaises(gate.ImageGateError):
            gate.recipe_hash(self.root)

    def test_recipe_ancestor_symlink_escape_rejected(self):
        target = self.outside / "deploy"
        (self.root / "deploy").rename(target)
        self.symlink(self.root / "deploy", target, directory=True)
        with self.assertRaises(gate.ImageGateError):
            gate.recipe_hash(self.root)

    def test_recipe_file_symlink_escape_rejected(self):
        target = self.outside / "external.txt"
        target.write_text("synthetic external fixture", encoding="utf-8")
        self.symlink(self.recipe / "external.txt", target)
        with self.assertRaises(gate.ImageGateError):
            gate.recipe_hash(self.root)

    def test_recipe_link_guard_without_host_link_privilege(self):
        original = Path.is_symlink

        def linked(path):
            return path == self.recipe or original(path)

        with (
            patch.object(Path, "is_symlink", linked),
            self.assertRaises(gate.ImageGateError),
        ):
            gate.recipe_hash(self.root)

    def test_report_hash_change_rejected(self):
        self.report_path.write_text("{}", encoding="utf-8")
        self.reject()

    def test_report_traversal_path_rejected(self):
        self.record["report"] = "../outside/report.json"
        self.reject()

    def test_report_symlink_escape_rejected(self):
        target = self.outside / "report.json"
        self.report_path.rename(target)
        self.symlink(self.report_path, target)
        self.reject()

    def test_record_symlink_escape_rejected_before_inspection(self):
        target = self.outside / "storage-image-lock.json"
        target.write_text(json.dumps(self.record), encoding="utf-8")
        self.symlink(self.root / gate.RECORD, target)
        with patch.object(gate, "_run", return_value=IMAGE_ID) as call:
            with self.assertRaises(gate.ImageGateError):
                gate.verify(["docker"], {}, self.root)
            call.assert_not_called()

    def test_record_link_guard_without_host_link_privilege(self):
        original = Path.is_symlink

        def linked(path):
            return path == self.root / gate.RECORD or original(path)

        with (
            patch.object(Path, "is_symlink", linked),
            patch.object(gate, "_run") as call,
        ):
            with self.assertRaises(gate.ImageGateError):
                gate.verify(["docker"], {}, self.root)
            call.assert_not_called()

    def test_build_refuses_linked_record_before_external_work(self):
        original = Path.is_symlink

        def linked(path):
            return path == self.root / gate.RECORD or original(path)

        with (
            patch.object(Path, "is_symlink", linked),
            patch.object(gate, "_run", return_value=IMAGE_ID) as call,
            patch("builtins.print"),
        ):
            with self.assertRaises(gate.ImageGateError):
                gate.build(["docker"], {}, self.root)
            call.assert_not_called()

    def test_report_for_different_image_cannot_be_rebound_by_hash(self):
        self.report["Metadata"]["ImageID"] = "sha256:" + "d4" * 32
        self.rehash_report()
        self.reject()

    def test_archive_content_tamper_rejected(self):
        with self.archive_path.open("ab") as stream:
            stream.write(b"changed after scan")
        self.reject()

    def test_archive_path_escape_rejected(self):
        self.record["archive"] = "../outside/untrusted.tar"
        self.reject()

    def test_config_id_cannot_be_rebound(self):
        self.record["config_id"] = IMAGE_ID
        self.reject()

    def test_archive_config_tamper_cannot_be_hidden_by_rehash(self):
        members = dict(FIXTURE_MEMBERS)
        members["blobs/sha256/" + CONFIG_ID.split(":")[1]] = b"{}"
        write_archive(self.archive_path, members)
        self.record["archive_sha256"] = hashlib.sha256(self.archive_path.read_bytes()).hexdigest()
        self.reject()

    def test_docker29_manifest_id_binds_distinct_config(self):
        self.assertNotEqual(IMAGE_ID, CONFIG_ID)
        identity = gate.archive_identity(self.archive_path, IMAGE_ID)
        self.assertEqual(CONFIG_ID, identity["config_id"])

    def test_oci_archive_supports_classic_config_id(self):
        identity = gate.archive_identity(self.archive_path, CONFIG_ID)
        self.assertEqual(CONFIG_ID, identity["config_id"])

    def test_unrelated_inspected_id_rejected(self):
        with self.assertRaises(gate.ImageGateError):
            gate.archive_identity(self.archive_path, "sha256:" + "e5" * 32)

    def test_legacy_archive_config_and_layers_verified(self):
        layer = b"legacy synthetic layer"
        config = json_bytes(
            {
                "os": "linux",
                "architecture": "amd64",
                "rootfs": {"type": "layers", "diff_ids": [digest(layer)]},
            }
        )
        identifier = digest(config)
        name = identifier.split(":")[1] + ".json"
        members = {
            name: config,
            "one/layer.tar": layer,
            "manifest.json": json_bytes([{"Config": name, "Layers": ["one/layer.tar"]}]),
        }
        write_archive(self.archive_path, members)
        self.assertEqual(
            identifier,
            gate.archive_identity(self.archive_path, identifier)["config_id"],
        )
        members["one/layer.tar"] = b"tampered layer"
        write_archive(self.archive_path, members)
        with self.assertRaises(gate.ImageGateError):
            gate.archive_identity(self.archive_path, identifier)

    def test_oci_layer_tamper_rejected(self):
        members = dict(FIXTURE_MEMBERS)
        manifest = json.loads(members["blobs/sha256/" + IMAGE_ID.split(":")[1]])
        layer_name = "blobs/sha256/" + manifest["layers"][0]["digest"].split(":")[1]
        members[layer_name] = b"tampered layer"
        write_archive(self.archive_path, members)
        with self.assertRaises(gate.ImageGateError):
            gate.archive_identity(self.archive_path, IMAGE_ID)

    def test_archive_paths_never_extracted(self):
        members = dict(FIXTURE_MEMBERS, **{"../outside.txt": b"synthetic"})
        write_archive(self.archive_path, members)
        with self.assertRaises(gate.ImageGateError):
            gate.archive_identity(self.archive_path, IMAGE_ID)
        self.assertFalse((self.sandbox / "outside.txt").exists())

    def test_compatibility_manifest_must_agree_with_oci(self):
        members = dict(FIXTURE_MEMBERS)
        members["manifest.json"] = json_bytes([{"Config": "other.json", "Layers": []}])
        members["other.json"] = b"{}"
        write_archive(self.archive_path, members)
        with self.assertRaises(gate.ImageGateError):
            gate.archive_identity(self.archive_path, IMAGE_ID)

    def test_report_without_image_identity_rejected(self):
        del self.report["Metadata"]["ImageID"]
        self.rehash_report()
        self.reject()

    def test_non_container_scan_report_rejected(self):
        self.report["ArtifactType"] = "filesystem"
        self.rehash_report()
        self.reject()

    def test_empty_report_results_are_not_a_clean_scan(self):
        self.report["Results"] = []
        self.rehash_report()
        self.reject()

    def test_both_os_and_go_dependency_coverage_are_required(self):
        original = list(self.report["Results"])
        for target in original:
            with self.subTest(remaining_class=target["Class"]):
                self.report["Results"] = [target]
                self.rehash_report()
                self.reject()

    def test_high_and_critical_findings_block_even_with_matching_hash(self):
        for severity in ("HIGH", "CRITICAL"):
            with self.subTest(severity=severity):
                self.report["Results"][0]["Vulnerabilities"] = [
                    {"VulnerabilityID": "SYNTHETIC-0001", "Severity": severity}
                ]
                self.rehash_report()
                self.reject()

    def test_low_medium_findings_remain_visible_without_false_zero_claim(self):
        self.report["Results"][0]["Vulnerabilities"] = [
            {"VulnerabilityID": "SYNTHETIC-0001", "Severity": "LOW"},
            {"VulnerabilityID": "SYNTHETIC-0002", "Severity": "MEDIUM"},
        ]
        self.assertEqual({"LOW": 1, "MEDIUM": 1}, gate.scan_findings(self.report))

    def test_malformed_severity_cannot_bypass_high_gate(self):
        self.report["Results"][0]["Vulnerabilities"] = [{"Severity": "high"}]
        self.rehash_report()
        self.reject()

    def test_invalid_report_target_returns_safe_error(self):
        self.report["Results"] = [None]
        self.rehash_report()
        self.reject()

    def test_verify_uses_only_reviewed_local_tag(self):
        (self.root / gate.RECORD).write_text(json.dumps(self.record), encoding="utf-8")
        with patch.object(gate, "_run", return_value=IMAGE_ID) as call:
            gate.verify(["docker", "--context", "desktop-linux"], {}, self.root)
        self.assertEqual(
            [
                "docker",
                "--context",
                "desktop-linux",
                "image",
                "inspect",
                "--format",
                "{{.Id}}",
                gate.TAG,
            ],
            call.call_args.args[0],
        )

    def test_build_failure_does_not_create_a_passing_lock(self):
        with (
            patch.object(gate, "_run", side_effect=gate.ImageGateError("synthetic failure")),
            patch("builtins.print"),
            self.assertRaises(gate.ImageGateError),
        ):
            gate.build(["docker"], {}, self.root)
        self.assertFalse((self.root / gate.RECORD).exists())

    def test_raw_subprocess_failure_output_never_leaks(self):
        process = subprocess.CompletedProcess(
            [], 1, "synthetic private stdout", "synthetic private stderr"
        )
        with (
            patch.object(gate.subprocess, "run", return_value=process),
            self.assertRaises(gate.ImageGateError) as captured,
        ):
            gate._run(["docker"], {}, self.root)
        self.assertNotIn("private", str(captured.exception))

    def test_timeout_is_safe_error(self):
        with (
            patch.object(
                gate.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("synthetic-private", 1),
            ),
            self.assertRaises(gate.ImageGateError) as captured,
        ):
            gate._run(["docker"], {}, self.root)
        self.assertNotIn("synthetic-private", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
