"""Owned local tooling services: TLS entry and telemetry. Never operates the KF/dev data stack."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
import hashlib
import os
from pathlib import Path
import secrets
import subprocess  # nosec B404 - fixed Docker CLI, reviewed local daemon and owned targets.
import time
import urllib.request

import yaml

import local_infra

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "deploy/dev-environment"
LOCAL = ROOT / "_local_artifacts/environment"
PROJECT = "ics-v1-tools"
LOCK = CONFIG / "images.lock.json"
TAGS = {
    "nginx": "ics-nginx:1.30.4-env.1",
    "prometheus": "ics-prometheus:3.13.3-env.1",
    "grafana": "ics-grafana:12.4.10-env.1",
    "otel": "ics-otelcol:0.160.0-env.1",
    "tempo": "ics-tempo:3.0.3-env.1",
    "loki": "ics-loki:3.7.7-env.1",
}


def recipe_digest(name):
    filename = "collector" if name == "otel" else name
    return hashlib.sha256(
        (CONFIG / "security" / (filename + ".Dockerfile")).read_bytes()
    ).hexdigest()


def run(args, timeout=180):
    result = subprocess.run(  # nosec B603 - argv from fixed commands, no shell or external CLI input.
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        # No environment values or raw container output in normal operator errors.
        raise RuntimeError(f"Environment operation failed: {args[1]}")
    return result.stdout.strip()


def docker():
    return local_infra.docker_prefix(local_infra.compose_environment(dict(os.environ)))


def owned_path(path):
    if path.is_symlink() or not path.resolve().is_relative_to(LOCAL.resolve()):
        raise ValueError("Tooling path escapes project artifacts")
    return path


def capture_images():
    records = {}
    for name, tag in TAGS.items():
        image = json.loads(run(docker() + ["image", "inspect", tag]))[0]
        if image["Config"].get("Labels", {}).get("org.ics.purpose") != "environment-toolkit":
            raise ValueError("Unreviewed derived image purpose")
        # Locally built derivatives have no registry RepoDigest. Compose uses the
        # exact content-addressed local ID, never a mutable tag or implicit pull.
        records[name] = {
            "tag": tag,
            "reference": image["Id"],
            "image_id": image["Id"],
            "recipe_sha256": recipe_digest(name),
        }
    LOCK.write_text(
        json.dumps({"schema_version": 2, "images": records}, indent=2) + "\n", encoding="utf-8"
    )


def images():
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    if data["schema_version"] != 2 or set(data["images"]) != set(TAGS):
        raise ValueError("Unexpected tooling image scope")
    for name, item in data["images"].items():
        if (
            item["tag"] != TAGS[name]
            or item["reference"] != item["image_id"]
            or item["recipe_sha256"] != recipe_digest(name)
        ):
            raise ValueError("Tooling tag not reviewed")
        actual = run(docker() + ["image", "inspect", item["reference"], "--format", "{{.Id}}"])
        if actual != item["image_id"]:
            raise ValueError("Tooling image identity mismatch")
    return data["images"]


def validate_audit(locked, audit):
    """Re-evaluate preserved raw reports and exact approved fixes at startup."""
    from environment_image_review import findings_from_report, review_findings

    age = datetime.now(UTC) - datetime.fromisoformat(audit["checked_at"])
    if (
        audit.get("status") not in {"PASS", "PASS_REVIEWED"}
        or not timedelta(0) <= age <= timedelta(days=3)
        or set(audit.get("images", {})) != set(locked)
    ):
        raise ValueError("Complete fresh image security audit required before startup")
    for name, value in locked.items():
        record = audit["images"][name]
        raw = owned_path(LOCAL / "image-audit" / (name + ".json")).read_bytes()
        if (
            record["image_id"] != value["image_id"]
            or hashlib.sha256(raw).hexdigest() != record["report_sha256"]
        ):
            raise ValueError("Security report/image identity mismatch")
        report = json.loads(raw)
        if report["Metadata"]["ImageID"] != record["config_id"]:
            raise ValueError("Security report config identity mismatch")
        findings = findings_from_report(report)
        review = review_findings(record, findings)
        if (
            review["unresolved_high_critical"]
            or len(findings) != record["high_critical"]
            or any(record.get(key) != expected for key, expected in review.items())
        ):
            raise ValueError("Unresolved findings or changed reviewed-fix evidence")


def credentials():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import ipaddress

    folder = owned_path(LOCAL / "secrets")
    folder.mkdir(parents=True, exist_ok=True)
    password = owned_path(folder / "grafana_password")
    if not password.exists():
        with password.open("x", encoding="utf-8") as output:
            output.write(secrets.token_urlsafe(32))
    key_path, cert_path = folder / "server.key", folder / "server.pem"
    if key_path.exists() != cert_path.exists():
        raise ValueError("Incomplete TLS identity; refusing silent replacement")
    if not key_path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ICS local development")])
        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=90))
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
                ),
                critical=False,
            )
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        with key_path.open("xb") as output:
            output.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        with cert_path.open("xb") as output:
            output.write(cert.public_bytes(serialization.Encoding.PEM))


def compose_config(locked):
    services = {}
    for name in TAGS:
        services[name] = {
            "image": locked[name]["reference"],
            "pull_policy": "never",
            "labels": {"org.ics.purpose": "environment-toolkit", "org.ics.workspace": str(ROOT)},
            "restart": "unless-stopped",
            "read_only": True,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "networks": ["telemetry"],
            "tmpfs": ["/tmp:rw,nosuid,nodev,size=64m"],  # nosec B108 - container-private bounded tmpfs.
            "mem_limit": "512m",
            "logging": {"driver": "json-file", "options": {"max-size": "5m", "max-file": "2"}},
        }

    def mount(source, dest, read_only=True):
        return {"type": "bind", "source": str(source), "target": dest, "read_only": read_only}

    obs = CONFIG / "observability"
    for name, target in {
        "otel": "/etc/otelcol-contrib/config.yaml",
        "prometheus": "/etc/prometheus/prometheus.yml",
        "tempo": "/etc/tempo.yaml",
        "loki": "/etc/loki/local-config.yaml",
    }.items():
        filename = "prometheus.yaml" if name == "prometheus" else name + ".yaml"
        services[name]["volumes"] = [mount(obs / filename, target)]
    for name in ("prometheus", "grafana", "tempo", "loki"):
        path = owned_path(LOCAL / "telemetry-data" / name)
        path.mkdir(parents=True, exist_ok=True)
        target = {"prometheus": "/prometheus", "grafana": "/var/lib/grafana"}.get(name, "/data")
        services[name].setdefault("volumes", []).append(mount(path, target, False))
    services["prometheus"].update(
        {
            "ports": ["127.0.0.1:29090:9090"],
            "command": [
                "--config.file=/etc/prometheus/prometheus.yml",
                "--storage.tsdb.retention.time=3d",
                "--storage.tsdb.retention.size=512MB",
            ],
            "mem_limit": "768m",
        }
    )
    services["otel"].update(
        {"ports": ["127.0.0.1:24317:4317", "127.0.0.1:24318:4318", "127.0.0.1:23333:13133"]}
    )
    services["tempo"].update(
        {"command": ["-config.file=/etc/tempo.yaml"], "ports": ["127.0.0.1:23200:3200"]}
    )
    services["loki"].update({"ports": ["127.0.0.1:23100:3100"]})
    services["grafana"]["volumes"] += [
        mount(obs / "datasources.yaml", "/etc/grafana/provisioning/datasources/local.yaml"),
        mount(LOCAL / "secrets/grafana_password", "/run/secrets/grafana_password"),
    ]
    services["grafana"].update(
        {
            "ports": ["127.0.0.1:23000:3000"],
            "environment": {
                "GF_SECURITY_ADMIN_USER": "admin",
                "GF_SECURITY_ADMIN_PASSWORD__FILE": "/run/secrets/grafana_password",  # nosec B105 - file path, not credential.
                "GF_USERS_ALLOW_SIGN_UP": "false",
                "GF_AUTH_ANONYMOUS_ENABLED": "false",
                "GF_ANALYTICS_REPORTING_ENABLED": "false",
                "GF_ANALYTICS_CHECK_FOR_UPDATES": "false",
                "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES": "false",
            },
        }
    )
    services["nginx"].update(
        {
            "user": "101:101",
            "entrypoint": ["nginx", "-g", "daemon off;"],
            "ports": ["127.0.0.1:28443:8443"],
            "networks": ["edge", "telemetry"],
            "volumes": [
                mount(CONFIG / "nginx.conf", "/etc/nginx/nginx.conf"),
                mount(LOCAL / "secrets/server.key", "/run/tls/server.key"),
                mount(LOCAL / "secrets/server.pem", "/run/tls/server.pem"),
            ],
        }
    )
    # Docker Desktop does not publish host bindings on an internal-only network.
    # Keep stores/Collector isolated; the existing Nginx edge owns loopback ingress.
    for name in ("grafana", "prometheus", "otel", "tempo", "loki"):
        services["nginx"]["ports"].extend(services[name].pop("ports"))
    return {
        "name": PROJECT,
        "services": services,
        "networks": {"telemetry": {"internal": True}, "edge": {}},
    }


def ownership():
    ids = run(
        docker() + ["ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}"]
    ).split()
    if not ids:
        return
    for record in json.loads(run(docker() + ["inspect", *ids])):
        labels = record["Config"]["Labels"]
        if (
            labels.get("org.ics.purpose") != "environment-toolkit"
            or labels.get("org.ics.workspace") != str(ROOT)
            or labels.get("com.docker.compose.service") not in TAGS
            or Path(labels.get("com.docker.compose.project.working_dir", "")).resolve()
            != LOCAL.resolve()
        ):
            raise ValueError("Unrecognized container in tooling project; no mutation")


def compose():
    return docker() + [
        "compose",
        "--project-directory",
        str(LOCAL),
        "-p",
        PROJECT,
        "-f",
        str(LOCAL / "services.compose.yaml"),
    ]


def health():
    import ssl

    context = ssl.create_default_context(cafile=str(LOCAL / "secrets/server.pem"))
    endpoints = {
        "nginx": "https://localhost:28443/environment/health",
        "grafana": "http://127.0.0.1:23000/api/health",
        "prometheus": "http://127.0.0.1:29090/-/ready",
        "otel": "http://127.0.0.1:23333/",
        "tempo": "http://127.0.0.1:23200/ready",
        "loki": "http://127.0.0.1:23100/ready",
    }
    for name, url in endpoints.items():
        with urllib.request.urlopen(  # nosec B310 - endpoints are fixed loopback HTTP/verified TLS constants.
            url, timeout=5, context=context if url.startswith("https:") else None
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"{name} not ready")
        print(f"Environment service ready: {name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["capture-images", "prepare", "up", "health", "status", "stop"]
    )
    args = parser.parse_args()
    LOCAL.mkdir(parents=True, exist_ok=True)
    if args.action == "capture-images":
        capture_images()
        return
    ownership()
    if args.action == "prepare":
        credentials()
        config = compose_config(images())
        (LOCAL / "services.compose.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
        )
        run(compose() + ["config", "--quiet"])
    elif args.action == "up":
        locked = images()
        audit = json.loads((LOCAL / "image-audit/summary.json").read_text(encoding="utf-8"))
        validate_audit(locked, audit)
        config = yaml.safe_load((LOCAL / "services.compose.yaml").read_text(encoding="utf-8"))
        if config != compose_config(images()):
            raise ValueError("Local tooling configuration differs from reviewed generator")
        run(compose() + ["up", "-d"], timeout=300)
        for attempt in range(45):
            try:
                health()
                return
            except (OSError, RuntimeError):
                if attempt == 44:
                    raise
                time.sleep(2)
    elif args.action == "health":
        health()
    elif args.action == "status":
        print(run(compose() + ["ps", "--format", "json"]))
    else:
        # Do not trust a possibly edited Compose file to select stop targets.
        ids = run(
            docker() + ["ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}"]
        ).split()
        if ids:
            run(docker() + ["stop", *ids])


if __name__ == "__main__":
    main()
