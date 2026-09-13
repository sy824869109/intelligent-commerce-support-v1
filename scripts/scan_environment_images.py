"""Scan only the newly selected environment image archives; no Docker socket in scanner."""

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import environment_services as env
from storage_image import SCANNER

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "_local_artifacts/environment/image-audit"
    folder.mkdir(parents=True, exist_ok=True)
    records = {}
    for name, item in env.images().items():
        archive = folder / f"{name}.tar"
        report = folder / f"{name}.json"
        if archive.exists():
            raise ValueError("Preserved image archive exists; inspect before overwriting")
        print(f"Scanning fixed image: {name}", flush=True)
        env.run(env.docker() + ["image", "save", "-o", str(archive), item["image_id"]], timeout=600)
        with archive.open("rb") as stream:
            archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        # Container-private tmpfs and project-only scan/cache mounts; no host credentials.
        env.run(
            env.docker()
            + [
                "run",
                "--rm",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=1g",
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
            ],
            timeout=1300,
        )
        data = json.loads(report.read_text(encoding="utf-8"))
        findings = [
            v
            for section in data.get("Results", [])
            for v in section.get("Vulnerabilities", [])
            if v["Severity"] in {"HIGH", "CRITICAL"}
        ]
        records[name] = {
            "reference": item["reference"],
            "image_id": item["image_id"],
            "archive_sha256": archive_hash,
            "high_critical": len(findings),
        }
        # Precisely delete only this newly generated archive; reports and source image remain.
        if archive.resolve().parent != folder.resolve() or archive.is_symlink():
            raise ValueError("Archive cleanup target changed")
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
    (folder / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
