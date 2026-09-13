"""Scan only the newly selected environment image archives; no Docker socket in scanner."""

from datetime import UTC, datetime
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

# Fixed local Docker argv only, without shell or user-provided commands.
import subprocess  # nosec B404

import environment_services as env
from storage_image import SCANNER

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = {
    "prometheus-lts": "prom/prometheus:v3.13.3",
    "grafana-maintained": "grafana/grafana:12.4.10",
    "nginx-patched": "ics-nginx:1.30.4-env.1",
}


def inspect_archive(path, image_id):
    """Prove the selected linux/amd64 OCI chain and inventory Java archive candidates.

    Docker Desktop exports an index with unpulled platforms. Only the selected
    platform is runnable here; missing foreign-platform blobs are not substituted.
    """
    if (
        path.is_symlink()
        or path.resolve().parent != (ROOT / "_local_artifacts/environment/image-audit").resolve()
    ):
        raise ValueError("Unexpected scan archive target")
    with path.open("rb") as stream:
        total_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        stream.seek(0)
        with tarfile.open(fileobj=stream) as archive:
            names = archive.getnames()
            if len(names) != len(set(names)):
                raise ValueError("Duplicate OCI member")

            def blob(digest):
                if (
                    not digest.startswith("sha256:")
                    or len(digest) != 71
                    or any(c not in "0123456789abcdef" for c in digest[7:])
                ):
                    raise ValueError("Invalid OCI digest")
                member = archive.getmember("blobs/sha256/" + digest[7:])
                if not member.isfile():
                    raise ValueError("OCI blob is not a regular file")
                with archive.extractfile(member) as content:
                    if hashlib.file_digest(content, "sha256").hexdigest() != digest[7:]:
                        raise ValueError("OCI blob hash mismatch")
                return member

            def document(digest):
                member = blob(digest)
                if member.size > 8 * 1024**2:
                    raise ValueError("Oversized OCI metadata")
                with archive.extractfile(member) as content:
                    return json.load(content)

            manifest = document(image_id)
            if "manifests" in manifest:
                candidates = [
                    m
                    for m in manifest["manifests"]
                    if m.get("platform", {}).get("os") == "linux"
                    and m.get("platform", {}).get("architecture") == "amd64"
                ]
                if len(candidates) != 1:
                    raise ValueError("Ambiguous OCI platform")
                manifest = document(candidates[0]["digest"])
            config_id = manifest["config"]["digest"]
            config = document(config_id)
            if (config.get("os"), config.get("architecture")) != ("linux", "amd64"):
                raise ValueError("Unexpected scan platform")
            java_count = 0
            for layer in manifest["layers"]:
                member = blob(layer["digest"])
                if member.size != layer["size"]:
                    raise ValueError("OCI layer size mismatch")
                with (
                    archive.extractfile(member) as content,
                    tarfile.open(fileobj=content, mode="r|*") as filesystem,
                ):
                    for index, entry in enumerate(filesystem):
                        if index > 1000000:
                            raise ValueError("Excessive image file inventory")
                        # Matches Trivy v0.74.0 jar analyzer Required(), including links.
                        if Path(entry.name).suffix.lower() in {".jar", ".war", ".ear", ".par"}:
                            java_count += 1
    return {"archive_sha256": total_hash, "config_id": config_id, "java_candidates": java_count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=sorted(CANDIDATES))
    args = parser.parse_args()
    folder = ROOT / "_local_artifacts/environment/image-audit"
    folder.mkdir(parents=True, exist_ok=True)
    records = {}
    if args.candidate:
        reference = CANDIDATES[args.candidate]
        inspected = json.loads(env.run(env.docker() + ["image", "inspect", reference]))[0]
        selected = {args.candidate: {"reference": reference, "image_id": inspected["Id"]}}
    else:
        selected = env.images()
    for name, item in selected.items():
        archive = folder / f"{name}.tar"
        report = folder / f"{name}.json"
        newly_exported = not archive.exists()
        print(f"Scanning fixed image: {name}", flush=True)
        if newly_exported:
            env.run(
                env.docker() + ["image", "save", "-o", str(archive), item["image_id"]], timeout=600
            )
        identity = inspect_archive(archive, item["image_id"])
        # Inventory is evidence only. All Trivy analyzers remain enabled; it fetches
        # its Java index automatically if eligible archives actually exist.
        metadata = json.loads((ROOT / "_local_artifacts/trivy-cache/db/metadata.json").read_text())
        fresh_db = datetime.fromisoformat(metadata["UpdatedAt"].replace("Z", "+00:00"))
        db_flags = (
            ["--skip-db-update"]
            if 0 <= (datetime.now(UTC) - fresh_db).total_seconds() < 86400
            else []
        )
        # Container-private tmpfs and project-only scan/cache mounts; no host credentials.
        subprocess.run(  # nosec B603
            env.docker()
            + [
                "run",
                "--rm",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=1g",  # nosec B108
                "--mount",
                f"type=bind,src={folder},dst=/scan",
                "--mount",
                f"type=bind,src={ROOT / '_local_artifacts/trivy-cache'},dst=/cache",
                SCANNER,
                "image",
                "--input",
                f"/scan/{name}.tar",
                "--cache-dir",
                "/cache",
                "--scanners",
                "vuln",
                "--severity",
                "HIGH,CRITICAL",
                "--ignore-unfixed=false",
                "--ignorefile",
                "/dev/null",
                "--format",
                "json",
                "--output",
                f"/scan/{name}.json",
                "--timeout",
                "20m",
                "--no-progress",
                "--list-all-pkgs",
                "--java-db-repository",
                "ghcr.io/aquasecurity/trivy-java-db:1",
            ]
            + db_flags,
            timeout=1300,
            check=True,
        )
        data = json.loads(report.read_text(encoding="utf-8"))
        if data.get("Metadata", {}).get("ImageID") != identity["config_id"] or not any(
            section.get("Packages") for section in data.get("Results", [])
        ):
            raise ValueError("Scanner identity or package inventory missing")
        findings = [
            v
            for section in data.get("Results", [])
            for v in section.get("Vulnerabilities", [])
            if v["Severity"] in {"HIGH", "CRITICAL"}
        ]
        records[name] = {
            "reference": item["reference"],
            "image_id": item["image_id"],
            **identity,
            "java_analysis": "NOT_APPLICABLE_NO_CANDIDATES"
            if not identity["java_candidates"]
            else "ENABLED",
            "database_updated_at": metadata["UpdatedAt"],
            "high_critical": len(findings),
        }
        # Precisely delete only this newly generated archive; reports and source image remain.
        if archive.resolve().parent != folder.resolve() or archive.is_symlink():
            raise ValueError("Archive cleanup target changed")
        if newly_exported:
            archive.unlink()
        if findings:
            print(f"Image security gate FAILED: {name}, findings={len(findings)}", flush=True)
        else:
            print(f"Image security gate PASS: {name}", flush=True)
    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "images": records,
        "status": "PASS" if all(r["high_critical"] == 0 for r in records.values()) else "FAILED",
    }
    # Candidate evidence must never replace the complete deployment acceptance report.
    summary = f"candidate-{args.candidate}.json" if args.candidate else "summary.json"
    (folder / summary).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
