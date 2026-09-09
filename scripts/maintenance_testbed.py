"""Isolated M01 patch compatibility lab; never copies real credentials or mounts real volumes."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import sys

import local_infra as infra
from maintenance_evidence import EVIDENCE
from storage_image import archive_identity
import verify_infra

ROOT = Path(__file__).resolve().parents[1]
LAB = EVIDENCE / "compatibility-lab"
PROJECT = "ics-v1-maint-20260909"
SOURCES = ("local_infra.py", "storage_config.py", "storage_probe.py", "verify_infra.py")
PORTS = {"MYSQL_PORT": "33306", "REDIS_PORT": "36379", "S3_PORT": "38333", "MILVUS_PORT": "39530"}


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def passed_images():
    result = {}
    for name in sorted(verify_infra.SERVICES):
        record = json.loads((EVIDENCE / (name + "-passed.json")).read_text(encoding="utf-8"))
        recipe_root = ROOT / "deploy/images" / name
        expected_files = {str(p.relative_to(ROOT)) for p in recipe_root.iterdir() if p.is_file()}
        if record.get("name") != name or set(record.get("recipe_hashes", {})) != expected_files:
            raise ValueError("Incomplete or mismatched recipe evidence")
        when = datetime.fromisoformat(record["scanned_at"])
        age = datetime.now(timezone.utc) - when
        if (
            age < timedelta(0)
            or age > timedelta(hours=24)
            or record["findings"]["HIGH"]
            or record["findings"]["CRITICAL"]
        ):
            raise ValueError("Candidate evidence is stale or failed")
        archive, report = Path(record["archive"]), Path(record["report"])
        if not all(p.resolve().is_relative_to(EVIDENCE.resolve()) for p in (archive, report)):
            raise ValueError("Evidence path escapes this maintenance")
        identity = archive_identity(archive, record["image_id"])
        if (
            identity["archive_sha256"] != record["archive_sha256"]
            or hashlib.sha256(report.read_bytes()).hexdigest() != record["report_sha256"]
        ):
            raise ValueError("Candidate evidence changed")
        for relative, expected in record["recipe_hashes"].items():
            path = (ROOT / relative).resolve()
            if (
                not path.is_relative_to((ROOT / "deploy/images" / name).resolve())
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected
            ):
                raise ValueError("Recipe changed after scanning")
        result[name] = record["reference"]
    return result


def prepare():
    if LAB.exists():
        raise ValueError("Existing lab retained; refusing to overwrite its identity or credentials")
    images = passed_images()
    # Validate the production blueprint BEFORE the only approved changes: namespace/images/ports.
    if verify_infra.check():
        raise ValueError("Original M01 configuration failed its guard")
    for port in PORTS.values():
        with socket.socket() as connection:
            connection.bind(("127.0.0.1", int(port)))
    folder = LAB / "deploy/compose"
    folder.mkdir(parents=True)
    (LAB / "scripts").mkdir()
    baseline = json.loads((ROOT / "deploy/compose/images.lock.json").read_text(encoding="utf-8"))
    # Keep exact helper snapshots, changing only the explicit isolated namespace and helper image.
    # All original ownership/resource/secret/loopback guards remain active in the lab.
    hashes = {}
    snapshot_hashes = {}
    for name in SOURCES:
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        hashes[name] = hashlib.sha256(source.encode("utf-8")).hexdigest()
        source = source.replace("ics-v1-dev", PROJECT)
        if name == "local_infra.py":
            source = source.replace(baseline["images"]["seaweedfs"], images["seaweedfs"])
        (LAB / "scripts" / name).write_text(source, encoding="utf-8")
        snapshot_hashes[name] = hashlib.sha256((LAB / "scripts" / name).read_bytes()).hexdigest()
    original = (ROOT / "deploy/compose/infra.compose.yml").read_text(encoding="utf-8")
    (folder / "infra.compose.yml").write_text(
        original.replace("ics-v1-dev", PROJECT), encoding="utf-8"
    )
    dump(folder / "images.lock.json", baseline)
    template = (ROOT / "deploy/compose/.env.example").read_text(encoding="utf-8")
    for key, port in PORTS.items():
        lines = template.splitlines()
        template = (
            "\n".join(key + "=" + port if line.startswith(key + "=") else line for line in lines)
            + "\n"
        )
    (folder / ".env.example").write_text(template, encoding="utf-8")
    dump(
        LAB / "lab.json",
        {
            "project": PROJECT,
            "root": str(LAB.resolve()),
            "source_hashes": hashes,
            "snapshot_hashes": snapshot_hashes,
            "baseline": baseline,
            "candidates": images,
        },
    )
    print("Prepared isolated synthetic lab; credentials and containers not yet created.")


def child(action, environment):
    path = LAB / "scripts/local_infra.py"
    result = infra.invoke(
        [sys.executable, str(path), action], environment, timeout=1500, required=False
    )
    logs = LAB / "logs"
    logs.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    (logs / (stamp + "-" + action + ".log")).write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    print(result.stdout)
    if result.returncode:
        raise RuntimeError("Isolated lab action failed: " + action)


def switch_spec(manifest, *, candidate):
    folder = LAB / "deploy/compose"
    previous = json.loads((folder / "images.lock.json").read_text(encoding="utf-8"))
    selected = manifest["candidates"] if candidate else manifest["baseline"]["images"]
    config = (folder / "infra.compose.yml").read_text(encoding="utf-8")
    for name in verify_infra.SERVICES:
        config = config.replace(previous["images"][name], selected[name])
    (folder / "infra.compose.yml").write_text(config, encoding="utf-8")
    previous["images"] = selected
    dump(folder / "images.lock.json", previous)


def run(action):
    manifest = json.loads((LAB / "lab.json").read_text(encoding="utf-8"))
    if manifest["project"] != PROJECT or manifest["root"] != str(LAB.resolve()):
        raise ValueError("Lab ownership mismatch")
    if set(manifest.get("snapshot_hashes", {})) != set(SOURCES):
        raise ValueError("Incomplete helper snapshot evidence")
    for name, expected in manifest["snapshot_hashes"].items():
        if hashlib.sha256((LAB / "scripts" / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Lab helper changed after preparation")
    environment = infra.compose_environment(dict(os.environ))
    environment.update(
        PYTHONUTF8="1",
        PYTHONDONTWRITEBYTECODE="1",
        TEMP=str(EVIDENCE / "tmp"),
        TMP=str(EVIDENCE / "tmp"),
    )
    if action == "stop":
        child("stop", environment)
        return
    if action != "test":
        raise ValueError("Unsupported action")
    if manifest["candidates"] != passed_images():
        raise ValueError("Candidate images changed")
    # Never automatically reset or rerun an initialized lab after a partial failure.
    if (LAB / "deploy/compose/.env").exists():
        raise ValueError("Lab already initialized; inspect existing evidence before any retry")
    try:
        child("init", environment)
        child("up", environment)
        child("health", environment)
        switch_spec(manifest, candidate=True)
        child(
            "upgrade", environment
        )  # Seed old images, replace in isolated lab, verify same volumes.
        child("health", environment)
        child("restart-test", environment)
        child("health", environment)
        dump(
            LAB / "compatibility-passed.json",
            {
                "status": "PASS",
                "scope": "isolated_synthetic_upgrade_and_restart",
                "candidates": manifest["candidates"],
                "at": datetime.now(timezone.utc).isoformat(),
            },
        )
    finally:
        # Keep this run's synthetic volumes and logs for inspection. Never delete or touch original data.
        child("stop", environment)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "test", "stop"])
    args = parser.parse_args()
    try:
        prepare() if args.action == "prepare" else run(args.action)
    except Exception as exc:
        print("Maintenance compatibility FAILED: " + type(exc).__name__)
        raise SystemExit(1) from None
