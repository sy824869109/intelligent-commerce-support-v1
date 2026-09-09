"""M01 20260909 candidate archive gates; never changes running containers or image locks."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

import local_infra as infra
from milvus_scan import scan_findings
from storage_image import archive_identity, SCANNER

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "_local_artifacts/m01-security-20260909"
TAGS = {
    "etcd": "ics-etcd:3.6.14-ics.2",
    "seaweedfs": "ics-seaweedfs:4.45-m01-security.2",
    "milvus": "ics-milvus:2.6.23-ics.2",
}


def scan(name):
    environment = infra.compose_environment(dict(os.environ))
    docker = infra.docker_prefix(environment)
    locked = json.loads((ROOT / "deploy/compose/images.lock.json").read_text(encoding="utf-8"))
    tag = TAGS.get(name, locked["images"][name])
    image_id = infra.invoke(
        docker + ["image", "inspect", tag, "--format", "{{.Id}}"], environment
    ).stdout.strip()
    folder = EVIDENCE / (name + "-" + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    archive = folder / "image.tar"
    report_path = folder / "trivy.json"
    infra.invoke(
        docker + ["image", "save", "--output", str(archive), image_id], environment, timeout=600
    )
    # Full severity report retained. Mount only this run's artifact folder, never a Docker socket.
    result = infra.invoke(
        docker
        + [
            "run",
            "--rm",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user",
            "0:0",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=3g",
            "--mount",
            f"type=bind,src={folder},dst=/scan",
            SCANNER,
            "image",
            "--input",
            "/scan/image.tar",
            "--cache-dir",
            "/tmp/trivy",
            "--scanners",
            "vuln",
            "--list-all-pkgs",
            "--format",
            "json",
            "--output",
            "/scan/trivy.json",
            "--ignore-unfixed=false",
            "--ignorefile",
            "/dev/null",
            "--timeout",
            "20m",
        ],
        environment,
        timeout=1500,
        required=False,
    )
    (folder / "scanner.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("Candidate scanner execution failed")
    identity = archive_identity(archive, image_id)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        report.get("SchemaVersion") != 2
        or report.get("Metadata", {}).get("ImageID") != identity["config_id"]
    ):
        raise ValueError("Report is not bound to the candidate archive")
    targets = report.get("Results", [])
    if not targets:
        raise ValueError("Missing scan targets")
    if name == "milvus":
        scan_findings(report)
    elif name == "etcd":
        names = {t.get("Target") for t in targets if t.get("Type") == "gobinary"}
        if not {"usr/local/bin/etcd", "usr/local/bin/etcdctl", "usr/local/bin/etcdutl"} <= names:
            raise ValueError("Missing etcd binary coverage")
    elif not any(t.get("Class") == "os-pkgs" for t in targets):
        raise ValueError("Missing operating-system coverage")
    if name == "seaweedfs" and not any(
        t.get("Target") == "usr/bin/weed" and t.get("Type") == "gobinary" for t in targets
    ):
        raise ValueError("Missing SeaweedFS binary coverage")
    findings = [v for target in targets for v in target.get("Vulnerabilities") or []]
    for finding in findings:
        if finding.get("Severity", "UNKNOWN") not in {
            "UNKNOWN",
            "LOW",
            "MEDIUM",
            "HIGH",
            "CRITICAL",
        }:
            raise ValueError("Unrecognized vulnerability severity")
    if name in TAGS:
        expected_grpc = (
            "v1.85.0-dev.0.20260825072537-93e31b48545e" if name == "seaweedfs" else "v1.83.2"
        )
        go_targets = [t for t in targets if t.get("Type") == "gobinary"]
        for target in go_targets:
            versions = {
                p.get("Version")
                for p in target.get("Packages", [])
                if p.get("Name") == "google.golang.org/grpc"
            }
            if versions != {expected_grpc}:
                raise ValueError("Candidate binary does not contain the reviewed gRPC module")
    counts = {
        severity: sum(v.get("Severity", "UNKNOWN") == severity for v in findings)
        for severity in ("UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL")
    }
    record = {
        "name": name,
        "image_id": image_id,
        "reference": tag.split("@")[0] + "@" + image_id,
        "archive": str(archive),
        "report": str(report_path),
        **identity,
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "findings": counts,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "recipe_hashes": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "deploy/images" / name).iterdir())
            if p.is_file()
        },
    }
    (folder / "evidence.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    if counts["HIGH"] or counts["CRITICAL"]:
        print(json.dumps({"name": name, "findings": counts, "evidence": str(folder)}))
        raise RuntimeError("Candidate still contains HIGH/CRITICAL")
    (EVIDENCE / (name + "-passed.json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"name": name, "image_id": image_id, "findings": counts, "evidence": str(folder)}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=["mysql", "redis", "etcd", "seaweedfs", "milvus"])
    try:
        scan(parser.parse_args().name)
    except Exception as exc:
        print("Maintenance evidence FAILED: " + type(exc).__name__)
        raise SystemExit(1) from None
