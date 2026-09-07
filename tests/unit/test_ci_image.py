"""M01 image CI policy tests; they do not claim a Docker build or vulnerability scan ran."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_ci as ci  # noqa: E402


class ImageWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = ci.parse_workflow(
            (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        )
        self.stages = json.loads((ROOT / ".github/ci-stages.json").read_text(encoding="utf-8"))
        self.directory = tempfile.TemporaryDirectory(prefix="ics-image-ci-policy-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for relative in ci.IMAGE_DOCKERFILES:
            marker = self.root / relative
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("# Synthetic path marker only; never built.\n", encoding="utf-8")
        self.job = self.workflow["jobs"]["image-build"]

    def validate(self):
        return ci.validate_workflow(self.workflow, self.stages, self.root)

    def assert_rejected(self):
        self.assertTrue(self.validate())

    def test_reviewed_real_commands_accepted(self):
        self.assertEqual([], self.validate())
        self.assertEqual("ACTIVE", self.stages["stages"]["image-build"]["state"])

    def test_milvus_build_parallelism_is_bounded_and_not_single_threaded(self):
        dockerfile = (ROOT / "deploy/images/milvus/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ENV MAKEFLAGS=-j2", dockerfile)
        self.assertIn("ENV jobs=2", dockerfile)
        self.assertNotIn("ENV MAKEFLAGS=-j1", dockerfile)

    def test_image_job_cannot_be_skipped(self):
        self.job["if"] = "${{ false }}"
        self.assert_rejected()

    def test_image_step_cannot_be_skipped(self):
        self.job["steps"][-1]["if"] = "${{ false }}"
        self.assert_rejected()

    def test_job_cannot_swallow_failure(self):
        self.job["continue-on-error"] = "true"
        self.assert_rejected()

    def test_scan_step_cannot_swallow_failure(self):
        self.job["steps"][-1]["continue-on-error"] = "true"
        self.assert_rejected()

    def test_build_cannot_be_fake_echo(self):
        self.job["steps"][1]["run"] = 'echo "image build passed"'
        self.assert_rejected()

    def test_scan_cannot_be_fake_echo(self):
        self.job["steps"][-1]["run"] = 'echo "vulnerability scan passed"'
        self.assert_rejected()

    def test_export_step_required(self):
        del self.job["steps"][2]
        self.assert_rejected()

    def test_scanner_digest_cannot_float(self):
        self.job["steps"][-1]["run"] = self.job["steps"][-1]["run"].replace(
            ci.TRIVY_IMAGE, "aquasec/trivy:0.74.0"
        )
        self.assert_rejected()

    def test_scanner_exit_code_must_fail(self):
        self.job["steps"][-1]["run"] = self.job["steps"][-1]["run"].replace(
            "--exit-code 1", "--exit-code 0"
        )
        self.assert_rejected()

    def test_unfixed_high_vulnerabilities_not_ignored(self):
        self.job["steps"][-1]["run"] = self.job["steps"][-1]["run"].replace(
            "--ignore-unfixed=false", "--ignore-unfixed=true"
        )
        self.assert_rejected()

    def test_scan_cannot_ignore_high_severity(self):
        self.job["steps"][-1]["run"] = self.job["steps"][-1]["run"].replace(
            "--severity HIGH,CRITICAL", "--severity CRITICAL"
        )
        self.assert_rejected()

    def test_archive_mount_cannot_be_writable(self):
        self.job["steps"][-1]["run"] = self.job["steps"][-1]["run"].replace(
            "dst=/scan,readonly", "dst=/scan"
        )
        self.assert_rejected()

    def test_docker_socket_cannot_be_mounted(self):
        self.job["steps"][-1]["run"] = self.job["steps"][-1]["run"].replace(
            "docker run --rm", "docker run --rm -v /var/run/docker.sock:/var/run/docker.sock"
        )
        self.assert_rejected()

    def test_repository_cannot_be_mounted_to_scanner(self):
        self.job["steps"][-1]["run"] = self.job["steps"][-1]["run"].replace(
            "src=$RUNNER_TEMP/ics-image-scan", "src=$GITHUB_WORKSPACE"
        )
        self.assert_rejected()

    def test_build_context_cannot_expand(self):
        self.job["steps"][1]["run"] = (
            self.job["steps"][1]["run"].removesuffix("deploy/images/seaweedfs") + "."
        )
        self.assert_rejected()

    def test_job_permissions_cannot_expand(self):
        self.job["permissions"] = {"contents": "read", "packages": "write"}
        self.assert_rejected()

    def test_workflow_permissions_cannot_expand(self):
        self.workflow["permissions"]["packages"] = "write"
        self.assert_rejected()

    def test_workflow_environment_cannot_disable_scanner(self):
        self.workflow["env"] = {"TRIVY_SKIP_DB_UPDATE": "true"}
        self.assert_rejected()

    def test_image_environment_cannot_override_scanner(self):
        self.job["env"] = {"TRIVY_IGNORE_UNFIXED": "true"}
        self.assert_rejected()

    def test_extra_publish_step_rejected(self):
        self.job["steps"].append({"run": "docker push ics-seaweedfs:ci"})
        self.assert_rejected()

    def test_foundation_dependency_required(self):
        del self.job["needs"]
        self.assert_rejected()

    def test_image_timeout_cannot_exceed_180_minutes(self):
        self.job["timeout-minutes"] = "181"
        self.assert_rejected()

    def test_foundation_timeout_not_relaxed(self):
        self.workflow["jobs"]["foundation"]["timeout-minutes"] = "45"
        self.assert_rejected()

    def test_reviewed_image_cannot_return_to_placeholder(self):
        self.stages["stages"]["image-build"]["state"] = "NOT_IMPLEMENTED"
        self.assert_rejected()

    def test_image_marker_globs_cannot_be_removed(self):
        self.stages["stages"]["image-build"]["markers"] = [ci.IMAGE_DOCKERFILES[0]]
        self.assert_rejected()

    def test_approved_input_cannot_expand_silently(self):
        self.stages["stages"]["image-build"]["reviewed_inputs"].append("apps/api/Dockerfile")
        self.assert_rejected()

    def test_missing_dockerfile_blocks_activation(self):
        with tempfile.TemporaryDirectory(prefix="ics-no-image-") as directory:
            self.assertTrue(ci.validate_workflow(self.workflow, self.stages, Path(directory)))

    def test_new_dockerfile_in_all_original_locations_requires_review(self):
        for name in ("Dockerfile", "apps/api/Dockerfile", "deploy/extra/Dockerfile.debug"):
            with self.subTest(name=name):
                marker = self.root / name
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text("# Unreviewed synthetic marker.\n", encoding="utf-8")
                self.assert_rejected()

    def test_unimplemented_application_stage_stays_skipped(self):
        for name in ci.STAGES - {"image-build"}:
            self.assertEqual("NOT_IMPLEMENTED", self.stages["stages"][name]["state"])
            self.assertEqual("${{ false }}", self.workflow["jobs"][name]["if"])

    def test_application_cannot_be_falsely_marked_active(self):
        self.stages["stages"]["backend"]["state"] = "ACTIVE"
        self.assert_rejected()

    def test_path_filter_cannot_skip_image_changes(self):
        self.workflow["on"]["push"]["paths"] = ["README.md"]
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
