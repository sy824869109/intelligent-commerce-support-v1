"""Validate foundation/M01 image CI and scan tracked assets without exposing matches.

This is a small repository safety baseline, not full SAST, vulnerability scanning,
Git-history secret scanning or business acceptance. YAML is parsed, never executed.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION_REFS = {
    "actions/checkout": "de0fac2e4500dabe0009e67214ff5f5447ce83dd",
    "actions/setup-python": "a309ff8b426b58ec0e2a45f0f869d46889d02405",
    "conda-incubator/setup-miniconda": "fc2d68f6413eb2d87b895e92f8584b5b94a10167",
}
STAGES = {"backend", "frontend", "contracts", "security-audit", "image-build"}
IMAGE_DOCKERFILES = [
    "deploy/images/etcd/Dockerfile",
    "deploy/images/milvus/Dockerfile",
    "deploy/images/mysql/Dockerfile",
    "deploy/images/redis/Dockerfile",
    "deploy/images/seaweedfs/Dockerfile",
]
IMAGE_MARKERS = ["Dockerfile*", "apps/**/Dockerfile*", "deploy/**/Dockerfile*"]
TRIVY_IMAGE = (
    "aquasec/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
)
IMAGE_BUILD_COMMAND = (
    "for attempt in 1 2 3; do\n"
    "  if docker build --pull --provenance=false --sbom=false --progress=plain "
    '--platform=linux/amd64 --file "deploy/images/${{ matrix.path }}/Dockerfile" '
    '--tag "ics-${{ matrix.path }}:ci" "deploy/images/${{ matrix.path }}"; then\n'
    "    exit 0\n"
    "  fi\n"
    '  if [ "$attempt" -eq 3 ]; then\n'
    "    exit 1\n"
    "  fi\n"
    "  sleep 15\n"
    "done"
)
IMAGE_EXPORT_COMMAND = (
    'mkdir -p "$RUNNER_TEMP/ics-image-scan"\n'
    'docker image save --output "$RUNNER_TEMP/ics-image-scan/${{ matrix.path }}.tar" '
    '"ics-${{ matrix.path }}:ci"'
)
IMAGE_SCAN_COMMAND = (
    'docker run --rm --read-only --user "$(id -u):$(id -g)" --cap-drop=ALL '
    "--security-opt=no-new-privileges --tmpfs /tmp:rw,nosuid,nodev,size=3g \\\n"
    '  --mount "type=bind,src=$RUNNER_TEMP/ics-image-scan,dst=/scan,readonly" \\\n'
    f"  {TRIVY_IMAGE} \\\n"
    '  image --input "/scan/${{ matrix.path }}.tar" --cache-dir /tmp/trivy --scanners vuln '
    "--severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed=false "
    "--ignorefile /dev/null --timeout 20m"
)
FORBIDDEN_PARTS = {
    "references",
    "legacy",
    ".venv",
    ".conda",
    "node_modules",
    "secrets",
    "model-cache",
    "models",
    "uploads",
    "volumes",
}
FORBIDDEN_SUFFIXES = {
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".pem",
    ".key",
    ".p12",
    ".pt",
    ".pth",
    ".onnx",
    ".safetensors",
    ".gguf",
}
TOKEN_PATTERN = re.compile(
    rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
    rb"sk-(?:proj-)?[A-Za-z0-9_-]{32,}|AKIA[A-Z0-9]{16})"
)
PRIVATE_KEY_PATTERN = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


class UniqueLoader(yaml.BaseLoader):
    """Preserve YAML 'on' as text and reject duplicate mapping keys everywhere."""

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError("Duplicate YAML mapping key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def parse_workflow(content: str) -> dict:
    """Load plain YAML data without YAML 1.1 boolean-key surprises."""
    result = yaml.load(content, Loader=UniqueLoader)
    if not isinstance(result, dict):
        raise ValueError("Workflow must be a mapping")
    return result


def validate_image_job(job: dict, stage: dict, root: Path) -> list[str]:
    """All five reviewed dependency recipes are built and scanned; no fake build/scan."""
    errors = []
    expected_stage = {
        "state": "ACTIVE",
        "enable_by": "M01 reviewed five-service dependency recipes",
        "markers": IMAGE_MARKERS,
        "reviewed_inputs": IMAGE_DOCKERFILES,
    }
    if stage != expected_stage:
        errors.append("Image stage must preserve reviewed ACTIVE state and all runtime markers")
    # Scan the full existing marker set: a new application image needs its own review.
    actual_inputs = {
        path.relative_to(root).as_posix()
        for pattern in IMAGE_MARKERS
        for path in root.glob(pattern)
        if path.is_file()
    }
    if actual_inputs != set(IMAGE_DOCKERFILES):
        errors.append("Image inputs must match all five reviewed dependency recipes")
    expected_job = {
        "name": "Reviewed ${{ matrix.name }} image build and vulnerability gate",
        "needs": "foundation",
        "runs-on": "ubuntu-24.04",
        "timeout-minutes": "180",
        "strategy": {
            "fail-fast": "false",
            "matrix": {
                "include": [
                    {"name": "MySQL", "path": "mysql"},
                    {"name": "Redis", "path": "redis"},
                    {"name": "etcd", "path": "etcd"},
                    {"name": "SeaweedFS", "path": "seaweedfs"},
                    {"name": "Milvus", "path": "milvus"},
                ]
            },
        },
        "defaults": {"run": {"shell": "bash"}},
        "steps": [
            {
                "name": "Checkout reviewed image recipes",
                "uses": "actions/checkout@" + ACTION_REFS["actions/checkout"],
                "with": {"persist-credentials": "false", "fetch-depth": "2"},
            },
            {
                "name": "Build reviewed dependency image without publishing",
                "run": IMAGE_BUILD_COMMAND,
            },
            {
                "name": "Export only the built image for isolated scanning",
                "run": IMAGE_EXPORT_COMMAND,
            },
            {
                "name": "Scan locked image archive and fail on HIGH or CRITICAL",
                "run": IMAGE_SCAN_COMMAND,
            },
        ],
    }
    normalized_job = dict(job)
    normalized_job["steps"] = [dict(step) for step in job.get("steps", [])]
    for step in normalized_job["steps"]:
        if isinstance(step.get("run"), str):
            step["run"] = step["run"].strip()
    if normalized_job != expected_job:
        errors.append("Image build/scan must use the exact unskipped least-privilege real commands")
    return errors


def validate_workflow(workflow: dict, stages: dict, root: Path) -> list[str]:
    """Keep application placeholders honest and enforce the reviewed image activation."""
    errors = []
    if set(workflow) != {"name", "on", "permissions", "concurrency", "jobs"}:
        errors.append("Unexpected workflow-level overrides, environment or execution inputs")
    triggers = workflow.get("on", {})
    if set(triggers) != {"push", "pull_request", "workflow_dispatch"}:
        errors.append("Only push/pull_request/workflow_dispatch triggers are allowed")
    if workflow.get("permissions") != {"contents": "read"}:
        errors.append("Workflow must use contents: read only")
    for event in ("push", "pull_request"):
        if triggers.get(event, {}) != {"branches": ["main", "codex/**"]}:
            errors.append(f"Missing branch coverage: {event}")
    jobs = workflow.get("jobs", {})
    if set(jobs) != STAGES | {"foundation"}:
        errors.append("Workflow job set does not match the foundation contract")
    if stages.get("schema_version") != 1 or set(stages.get("stages", {})) != STAGES:
        errors.append("CI stage manifest schema or stages do not match")
    for name, job in jobs.items():
        if "continue-on-error" in job or "permissions" in job:
            errors.append(f"Job must not bypass failures or expand permissions: {name}")
        try:
            timeout_limit = 180 if name == "image-build" else 15
            if not 1 <= int(job.get("timeout-minutes", 0)) <= timeout_limit:
                errors.append(f"Job requires bounded timeout: {name}")
        except (ValueError, TypeError):
            errors.append(f"Invalid timeout: {name}")
        for step in job.get("steps", []):
            if "continue-on-error" in step:
                errors.append(f"Step bypasses failure: {name}")
            if "uses" in step:
                action, _, sha = step["uses"].partition("@")
                if ACTION_REFS.get(action) != sha:
                    errors.append(f"Action must use reviewed immutable SHA: {action}")
                if (
                    action == "actions/checkout"
                    and step.get("with", {}).get("persist-credentials") != "false"
                ):
                    errors.append("Checkout must not persist credentials")
    foundation = jobs.get("foundation", {})
    if "if" in foundation:
        errors.append("Foundation checks cannot be conditional")
    expected_steps = [
        "Checkout",
        "Python from project baseline",
        "Windows Conda from project baseline",
        "Install hash-locked CI tools only",
        "Format, static checks, contracts baseline, asset safety and unit tests",
    ]
    steps = foundation.get("steps", [])
    bootstrap_conditions = {
        "Python from project baseline": "runner.os != 'Windows'",
        "Windows Conda from project baseline": "runner.os == 'Windows'",
    }
    for step in steps:
        if step.get("if") != bootstrap_conditions.get(step.get("name")):
            errors.append("Only the two reviewed OS bootstrap conditions are allowed")
    install_command = (
        "python -m pip install --require-hashes --only-binary=:all: -r ci/requirements.lock"
    )
    if not any(step.get("run", "").strip() == install_command for step in steps):
        errors.append("CI tools must be installed with the hash-locked binary-only command")
    if [step.get("name") for step in steps] != expected_steps:
        errors.append("Foundation steps must not silently disappear")
    if not any(step.get("run") == "python scripts/ci.py" for step in steps):
        errors.append("Foundation must run the real local CI entry point")
    if foundation.get("strategy", {}).get("matrix", {}).get("os") != [
        "ubuntu-24.04",
        "windows-2022",
    ]:
        errors.append("Linux and Windows runners are required")
    for name, stage in stages.get("stages", {}).items():
        if name == "image-build":
            errors.extend(validate_image_job(jobs.get(name, {}), stage, root))
            continue
        if stage.get("state") != "NOT_IMPLEMENTED" or not stage.get("markers"):
            errors.append(f"Stage activation requires replacing its skeleton contract: {name}")
        if jobs.get(name, {}).get("if") != "${{ false }}":
            errors.append(f"Unimplemented stage must be visibly skipped: {name}")
        for pattern in stage.get("markers", []):
            if any(path.is_file() for path in root.glob(pattern)):
                errors.append(f"Runtime input exists: activate real {name} checks before merging")
                break
    return errors


def asset_findings(relative: str, data: bytes) -> list[str]:
    """Return rule IDs only; never print secret values or matching source lines."""
    path = Path(relative)
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    reasons = []
    if parts & FORBIDDEN_PARTS or path.suffix.lower() in FORBIDDEN_SUFFIXES:
        reasons.append("forbidden-asset")
    if (name == ".env" or name.startswith(".env.")) and name != ".env.example":
        reasons.append("private-environment")
    if len(data) > 10 * 1024 * 1024:
        reasons.append("oversized-tracked-asset")
    if PRIVATE_KEY_PATTERN.search(data) or TOKEN_PATTERN.search(data):
        reasons.append("possible-secret")
    return reasons


def tracked_files(root: Path) -> list[Path]:
    """Use Git's tracked set; never crawl ignored local archives or environments."""
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    return [Path(item.decode("utf-8")) for item in output.split(b"\0") if item]


def main() -> int:
    """Fail closed on invalid CI configuration or tracked unsafe assets."""
    try:
        workflow = parse_workflow((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        stages = json.loads((ROOT / ".github/ci-stages.json").read_text(encoding="utf-8"))
        errors = validate_workflow(workflow, stages, ROOT)
        paths = tracked_files(ROOT)
        for relative in paths:
            path = ROOT / relative
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
                errors.append(f"Unsafe tracked link: {relative.as_posix()}")
                continue
            # Check size before reading potentially large newly tracked files.
            if path.stat().st_size > 10 * 1024 * 1024:
                errors.append(f"oversized-tracked-asset: {relative.as_posix()}")
                continue
            for rule in asset_findings(relative.as_posix(), path.read_bytes()):
                errors.append(f"{rule}: {relative.as_posix()}")
    except (OSError, ValueError, TypeError, yaml.YAMLError, subprocess.CalledProcessError):
        print("ci-policy-check: FAILED (unable to validate inputs; no content logged)")
        return 1
    for error in errors:
        print(error)
    print(f"ci-policy-check: {'FAILED' if errors else 'OK'}; tracked assets: {len(paths)}")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
