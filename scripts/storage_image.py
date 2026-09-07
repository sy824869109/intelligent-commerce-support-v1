"""新平台存储派生镜像的本机构建与扫描锁；不上传镜像、不读取源码外的密钥。

独立入口核对镜像 ID、构建输入哈希及扫描报告，三个证据缺一即拒绝。
尚未接入三服务 Compose；不会启动知识存储。产物仅保存在被忽略的 data/ 下。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

TAG = "ics-seaweedfs:4.45-m01-security.1"
SCANNER = (
    "aquasec/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
)
RECIPE = "deploy/images/seaweedfs"
RECORD = "data/m01-reports/storage-image-lock.json"
RECORD_VERSION = 2
_DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
_INDEX_TYPES = {
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
}
_MANIFEST_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}
_CONFIG_TYPES = {
    "application/vnd.oci.image.config.v1+json",
    "application/vnd.docker.container.image.v1+json",
}


class ImageGateError(ValueError):
    """只输出阶段，不回显容器/构建的原始输出。"""


def _json(data: bytes | str):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ImageGateError("Duplicate evidence JSON key")
            result[key] = value
        return result

    return json.loads(data, object_pairs_hook=unique)


def _evidence_path(root: Path, relative: str, suffix: str) -> Path:
    if not isinstance(relative, str) or not re.fullmatch(
        rf"data/m01-reports/seaweed-security-[a-f0-9]{{32}}\.{suffix}", relative
    ):
        raise ImageGateError("Unexpected local image evidence path")
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ImageGateError("Image evidence escapes the project")
    return path


def archive_identity(path: Path, image_id: str) -> dict[str, str]:
    """只读 tar，不解压：用内容哈希证明 Docker inspect ID 对应哪个 config ID。

    Docker 29/containerd 的 ID 可能是 OCI manifest/index digest；Trivy ImageID
    是 config digest。必须存在已校验的 root→child manifest→config 链，不能
    将任意两个 ID 配对。旧 Docker manifest.json 则要求 inspect ID 等于实际
    config 内容哈希，并核对各未压缩 layer 与 config.rootfs.diff_ids。
    调用方还须用 _evidence_path 限制路径；同一打开文件句柄完成总哈希与解析。
    """
    try:
        if not isinstance(image_id, str) or not _DIGEST.fullmatch(image_id):
            raise ImageGateError("Invalid image identity for archive verification")
        with path.open("rb") as stream:
            archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            stream.seek(0)
            with tarfile.open(fileobj=stream, mode="r:") as archive:
                members = {}
                for number, member in enumerate(archive):
                    name = member.name.rstrip("/")
                    pure = PurePosixPath(name)
                    if (
                        number >= 20000
                        or not name
                        or "\\" in name
                        or pure.is_absolute()
                        or ".." in pure.parts
                        or pure.as_posix() != name
                        or name in members
                        or not (member.isfile() or member.isdir())
                    ):
                        raise ImageGateError("Unsafe or duplicate image archive member")
                    members[name] = member
                checked: dict[str, str] = {}

                def member_hash(name: str) -> str:
                    member = members.get(name)
                    if member is None or not member.isfile():
                        raise ImageGateError("Referenced image archive member is missing")
                    if name not in checked:
                        with archive.extractfile(member) as content:
                            checked[name] = (
                                "sha256:" + hashlib.file_digest(content, "sha256").hexdigest()
                            )
                    return checked[name]

                def document(name: str):
                    member = members.get(name)
                    if member is None or not member.isfile() or member.size > 8 * 1024 * 1024:
                        raise ImageGateError("Invalid or oversized image metadata member")
                    with archive.extractfile(member) as content:
                        return _json(content.read())

                def descriptor_blob(descriptor: dict, *, metadata: bool):
                    digest = descriptor.get("digest")
                    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
                        raise ImageGateError("Invalid OCI descriptor digest")
                    name = "blobs/sha256/" + digest.split(":", 1)[1]
                    member = members.get(name)
                    if (
                        member is None
                        or not isinstance(descriptor.get("size"), int)
                        or descriptor["size"] != member.size
                        or member_hash(name) != digest
                    ):
                        raise ImageGateError("OCI descriptor size/content digest mismatch")
                    return document(name) if metadata else None

                def config_platform(config: dict) -> tuple[str, str]:
                    if not isinstance(config, dict) or not isinstance(config.get("rootfs"), dict):
                        raise ImageGateError("Invalid image config structure")
                    diff_ids = config["rootfs"].get("diff_ids")
                    if (
                        config["rootfs"].get("type") != "layers"
                        or not isinstance(diff_ids, list)
                        or not all(
                            isinstance(value, str) and _DIGEST.fullmatch(value)
                            for value in diff_ids
                        )
                    ):
                        raise ImageGateError("Invalid image config layer identities")
                    return config.get("os"), config.get("architecture")

                candidates: list[dict] = []
                if "index.json" in members:
                    if document("oci-layout") != {"imageLayoutVersion": "1.0.0"}:
                        raise ImageGateError("Unsupported OCI archive layout")
                    root_index = document("index.json")
                    if (
                        not isinstance(root_index, dict)
                        or root_index.get("schemaVersion") != 2
                        or root_index.get("mediaType") not in _INDEX_TYPES
                    ):
                        raise ImageGateError("Invalid OCI root index")

                    def walk(descriptor: dict, ancestry: tuple[str, ...] = ()):
                        if not isinstance(descriptor, dict) or len(ancestry) >= 8:
                            raise ImageGateError("Invalid or excessive OCI descriptor chain")
                        digest = descriptor.get("digest")
                        if digest in ancestry:
                            raise ImageGateError("Cyclic OCI descriptor chain")
                        node = descriptor_blob(descriptor, metadata=True)
                        if not isinstance(node, dict) or node.get("schemaVersion") != 2:
                            raise ImageGateError("Invalid OCI image manifest")
                        media_type = descriptor.get("mediaType")
                        if node.get("mediaType") != media_type:
                            raise ImageGateError("OCI manifest media type mismatch")
                        chain = ancestry + (digest,)
                        if media_type in _INDEX_TYPES:
                            children = node.get("manifests")
                            if not isinstance(children, list) or not 1 <= len(children) <= 64:
                                raise ImageGateError("Invalid OCI child manifest list")
                            for child in children:
                                walk(child, chain)
                        elif media_type in _MANIFEST_TYPES:
                            config_ref = node.get("config")
                            if (
                                not isinstance(config_ref, dict)
                                or config_ref.get("mediaType") not in _CONFIG_TYPES
                            ):
                                raise ImageGateError("Invalid OCI config descriptor")
                            config = descriptor_blob(config_ref, metadata=True)
                            platform = config_platform(config)
                            declared = descriptor.get("platform")
                            if declared is not None and (
                                not isinstance(declared, dict)
                                or (declared.get("os"), declared.get("architecture")) != platform
                            ):
                                raise ImageGateError("OCI platform does not match image config")
                            layers = node.get("layers")
                            if not isinstance(layers, list) or len(layers) != len(
                                config["rootfs"]["diff_ids"]
                            ):
                                raise ImageGateError("OCI layer count does not match config")
                            for layer in layers:
                                if not isinstance(layer, dict):
                                    raise ImageGateError("Invalid OCI layer descriptor")
                                descriptor_blob(layer, metadata=False)
                            config_id = config_ref["digest"]
                            if platform == ("linux", "amd64") and (
                                image_id in chain or image_id == config_id
                            ):
                                candidates.append(
                                    {
                                        "config_id": config_id,
                                        "layers": [
                                            "blobs/sha256/" + layer["digest"].split(":")[1]
                                            for layer in layers
                                        ],
                                    }
                                )
                        else:
                            raise ImageGateError("Unsupported OCI image manifest type")

                    roots = root_index.get("manifests")
                    if not isinstance(roots, list) or not 1 <= len(roots) <= 64:
                        raise ImageGateError("Invalid OCI root descriptor list")
                    for descriptor in roots:
                        walk(descriptor)
                    # Docker exports can contain both formats. The compatibility
                    # manifest must agree, otherwise a scanner might choose a
                    # different config than the OCI path proved above.
                    if "manifest.json" in members:
                        legacy = document("manifest.json")
                        if not isinstance(legacy, list) or len(legacy) != 1:
                            raise ImageGateError("Ambiguous Docker compatibility manifest")
                        config_name = legacy[0].get("Config")
                        compatibility_id = member_hash(config_name)
                        if (
                            len(candidates) != 1
                            or candidates[0]["config_id"] != compatibility_id
                            or legacy[0].get("Layers") != candidates[0]["layers"]
                        ):
                            raise ImageGateError(
                                "Docker and OCI archive config identities disagree"
                            )
                else:
                    legacy = document("manifest.json")
                    if (
                        not isinstance(legacy, list)
                        or len(legacy) != 1
                        or not isinstance(legacy[0], dict)
                    ):
                        raise ImageGateError("Ambiguous legacy Docker image archive")
                    entry = legacy[0]
                    config_name = entry.get("Config")
                    if not isinstance(config_name, str) or not re.fullmatch(
                        r"[a-f0-9]{64}\.json", config_name
                    ):
                        raise ImageGateError("Invalid legacy Docker config path")
                    config_id = member_hash(config_name)
                    if config_id != image_id or config_name != config_id.split(":")[1] + ".json":
                        raise ImageGateError("Legacy Docker config identity mismatch")
                    config = document(config_name)
                    if config_platform(config) != ("linux", "amd64"):
                        raise ImageGateError("Unexpected local image platform")
                    layers = entry.get("Layers")
                    if not isinstance(layers, list) or len(layers) != len(
                        config["rootfs"]["diff_ids"]
                    ):
                        raise ImageGateError("Legacy Docker layer count mismatch")
                    for name, diff_id in zip(layers, config["rootfs"]["diff_ids"]):
                        if not isinstance(name, str) or member_hash(name) != diff_id:
                            raise ImageGateError("Legacy Docker layer content mismatch")
                    candidates.append({"config_id": config_id, "layers": layers})
                if len(candidates) != 1:
                    raise ImageGateError("Archive does not uniquely bind the inspected image")
                return {
                    "archive_sha256": archive_hash,
                    "config_id": candidates[0]["config_id"],
                }
    except ImageGateError:
        raise
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        tarfile.TarError,
        EOFError,
    ):
        raise ImageGateError("Image archive identity evidence is invalid") from None


def recipe_hash(root: Path) -> str:
    folder = root / RECIPE
    if folder.is_symlink() or not folder.resolve().is_relative_to(root.resolve()):
        raise ImageGateError("Storage recipe directory escapes the project")
    digest = hashlib.sha256()
    paths = sorted(path for path in folder.rglob("*") if path.is_file())
    if not paths or not (folder / "Dockerfile").is_file():
        raise ImageGateError("Storage image recipe is missing")
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
            raise ImageGateError("Storage recipe path escapes the project")
        digest.update(path.relative_to(folder).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def _run(argv: list[str], environment: dict[str, str], root: Path, timeout: int = 60) -> str:
    try:
        process = subprocess.run(
            argv,
            env=environment,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise ImageGateError("Storage image operation failed or timed out") from None
    if process.returncode:
        raise ImageGateError("Storage image build/scan failed; no startup permitted")
    return process.stdout.strip()


def scan_findings(report: dict) -> dict[str, int]:
    if (
        not isinstance(report, dict)
        or report.get("SchemaVersion") != 2
        or report.get("ArtifactType") != "container_image"
        or not isinstance(report.get("Results"), list)
        or not report["Results"]
    ):
        raise ImageGateError("Vulnerability report is incomplete")
    if any(not isinstance(target, dict) for target in report["Results"]):
        raise ImageGateError("Vulnerability report contains invalid targets")
    covered = {(target.get("Class"), target.get("Type")) for target in report["Results"]}
    if not {("os-pkgs", "alpine"), ("lang-pkgs", "gobinary")} <= covered:
        raise ImageGateError("Storage scan must cover both operating system and Go binary")
    count: dict[str, int] = {}
    for target in report["Results"]:
        for finding in target.get("Vulnerabilities") or []:
            if not isinstance(finding, dict):
                raise ImageGateError("Vulnerability report contains invalid findings")
            severity = finding.get("Severity", "UNKNOWN")
            if severity not in {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                raise ImageGateError("Vulnerability severity is not a reviewed scanner value")
            count[severity] = count.get(severity, 0) + 1
    if count.get("HIGH", 0) or count.get("CRITICAL", 0):
        raise ImageGateError("Storage image still has HIGH/CRITICAL findings")
    return count


def validate_record(root: Path, record: dict, current_id: str) -> None:
    try:
        if (
            record["schema_version"] != RECORD_VERSION
            or record["tag"] != TAG
            or record["scanner"] != SCANNER
            or record["image_id"] != current_id
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", current_id)
            or record["recipe_sha256"] != recipe_hash(root)
        ):
            raise ImageGateError("Built image identity/input lock mismatch")
        scanned = datetime.fromisoformat(record["scanned_at"])
        age = datetime.now(UTC) - scanned
        if not timedelta(0) <= age <= timedelta(days=7):
            raise ImageGateError("Storage image scan expired; rebuild/rescan before startup")
        archive = _evidence_path(root, record["archive"], "tar")
        identity = archive_identity(archive, current_id)
        if (
            identity["archive_sha256"] != record["archive_sha256"]
            or identity["config_id"] != record["config_id"]
        ):
            raise ImageGateError("Image archive hash/config binding mismatch")
        report = _evidence_path(root, record["report"], "json")
        data = report.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["report_sha256"]:
            raise ImageGateError("Scan report hash mismatch")
        parsed = _json(data)
        if parsed.get("Metadata", {}).get("ImageID") != identity["config_id"]:
            raise ImageGateError("Scan report does not describe the archive-bound config ID")
        scan_findings(parsed)
    except ImageGateError:
        raise
    except (KeyError, TypeError, OSError, ValueError, AttributeError):
        raise ImageGateError("Local image gate evidence missing or invalid") from None


def verify(docker: list[str], environment: dict[str, str], root: Path) -> None:
    try:
        path = root / RECORD
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ImageGateError("Image lock escapes the project")
        record = _json(path.read_text(encoding="utf-8"))
        current_id = _run(
            docker + ["image", "inspect", "--format", "{{.Id}}", TAG], environment, root
        )
        validate_record(root, record, current_id)
    except OSError:
        raise ImageGateError(
            "Run build-image to create a verified local storage image first"
        ) from None


def build(docker: list[str], environment: dict[str, str], root: Path) -> dict:
    """只构建/扫描自己的精确 tag；失败不出具通过凭据，不操作已有服务。"""
    fingerprint = recipe_hash(root)
    record_path = root / RECORD
    if record_path.is_symlink() or not record_path.resolve().is_relative_to(root.resolve()):
        raise ImageGateError("Image lock path escapes the project")
    reports = root / "data/m01-reports"
    cache = root / "data/trivy-cache"
    for folder in (reports, cache):
        if folder.is_symlink() or not folder.resolve().is_relative_to(root.resolve()):
            raise ImageGateError("Image workspace escapes the project")
        folder.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex
    print(
        "Building pinned storage security image; upstream downloads/compilation may take minutes.",
        flush=True,
    )
    _run(
        docker
        + [
            "build",
            "--platform=linux/amd64",
            "--provenance=false",
            "--sbom=false",
            "--tag",
            TAG,
            RECIPE,
        ],
        environment,
        root,
        timeout=2700,
    )
    current_id = _run(docker + ["image", "inspect", "--format", "{{.Id}}", TAG], environment, root)
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", current_id):
        raise ImageGateError("Unexpected local image ID")
    archive = reports / f"seaweed-security-{identifier}.tar"
    output = reports / f"seaweed-security-{identifier}.json"
    _run(
        docker + ["image", "save", "--output", str(archive), current_id],
        environment,
        root,
        300,
    )
    archive = _evidence_path(root, archive.relative_to(root).as_posix(), "tar")
    identity = archive_identity(archive, current_id)
    print(
        "Scanning exact built image archive; no Docker socket or project source mounted.",
        flush=True,
    )
    _run(
        docker
        + [
            "run",
            "--rm",
            "--cpus",
            "2",
            "--memory",
            "1536m",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--mount",
            f"type=bind,source={archive},target=/input/image.tar,readonly",
            "--mount",
            f"type=bind,source={reports},target=/reports",
            "--mount",
            f"type=bind,source={cache},target=/root/.cache/trivy",
            SCANNER,
            "image",
            "--quiet",
            "--timeout",
            "15m",
            "--input",
            "/input/image.tar",
            "--scanners",
            "vuln",
            "--ignore-unfixed=false",
            "--ignorefile",
            "/dev/null",
            "--format",
            "json",
            "--output",
            f"/reports/{output.name}",
        ],
        environment,
        root,
        1200,
    )
    data = output.read_bytes()
    findings = scan_findings(json.loads(data))
    record = {
        "schema_version": RECORD_VERSION,
        "tag": TAG,
        "image_id": current_id,
        "config_id": identity["config_id"],
        "archive": archive.relative_to(root).as_posix(),
        "archive_sha256": identity["archive_sha256"],
        "recipe_sha256": fingerprint,
        "scanner": SCANNER,
        "scanned_at": datetime.now(UTC).isoformat(),
        "report": output.relative_to(root).as_posix(),
        "report_sha256": hashlib.sha256(data).hexdigest(),
        "findings": findings,
    }
    validate_record(root, record, current_id)
    # Recheck the target after the long build/scan, then atomically replace only
    # this generated record; never follow a changed target symlink on write.
    if record_path.is_symlink() or not record_path.resolve().is_relative_to(root.resolve()):
        raise ImageGateError("Image lock path changed during build")
    pending = reports / f"storage-image-lock-{identifier}.tmp"
    with pending.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, indent=2) + "\n")
    pending.replace(record_path)
    # Generated artifacts remain available for audit; nothing is deleted automatically.
    print("PASS image build + HIGH/CRITICAL gate; other severities remain in the full report.")
    return {"image_id": current_id, "findings": findings}


def main() -> int:
    """Independent image-only CLI; never starts a database or accepts remote Docker."""
    import local_infra

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "verify"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        environment = local_infra.compose_environment(dict(os.environ))
        docker = local_infra.docker_prefix(environment)
        if args.action == "build":
            print(json.dumps(build(docker, environment, root), indent=2))
        else:
            verify(docker, environment, root)
            print("PASS local image ID/archive/report binding; no service was started.")
    except (
        ImageGateError,
        local_infra.InfraError,
        OSError,
        ValueError,
        TypeError,
        subprocess.SubprocessError,
    ) as exc:
        detail = (
            str(exc)
            if isinstance(exc, (ImageGateError, local_infra.InfraError))
            else type(exc).__name__
        )
        print(f"storage-image FAILED: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
