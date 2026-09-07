"""Static M01 five-service Compose guard; never reads secrets or starts Docker."""

from __future__ import annotations
import json
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {"mysql", "redis", "etcd", "seaweedfs", "milvus"}
HOST_SERVICES = SERVICES - {"etcd"}
SECRET_NAMES = {
    "mysql_root_password",
    "mysql_password",
    "redis_password",
    "redis_config",
    "seaweed_s3_config",
    "seaweed_security_config",
    "milvus_config",
    "milvus_root_password",
}
IMAGE_PATTERN = re.compile(r"ics-[a-z0-9-]+:[A-Za-z0-9_.-]+@sha256:[a-f0-9]{64}")
INSTANCE = "${INFRA_INSTANCE_ID:?INFRA_INSTANCE_ID required}"


class ComposeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        keys = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise ValueError("Duplicate Compose key")
            keys.add(key)
        self.flatten_mapping(node)
        return super().construct_mapping(node, deep=deep)


def parse_compose(content: str) -> dict:
    value = yaml.load(content, Loader=ComposeLoader)
    if not isinstance(value, dict):
        raise TypeError("Compose must be a mapping")
    return value


def validate_compose(config: dict, lock: dict) -> list[str]:
    errors: list[str] = []
    services, images = config.get("services", {}), lock.get("images", {})
    if config.get("name") != "ics-v1-dev" or set(services) != SERVICES:
        errors.append("Exactly five isolated M01 services are required")
    if lock.get("schema_version") != 2 or set(images) != SERVICES:
        errors.append("Five-service image lock mismatch")
    if lock.get("high_critical") != {name: 0 for name in SERVICES}:
        errors.append("Every locked image requires zero HIGH/CRITICAL evidence")
    if any(key in config for key in ("include", "configs", "profiles")):
        errors.append("Unexpected additional Compose inputs")
    volumes = {f"{name}_data": {"labels": {"org.ics.instance": INSTANCE}} for name in SERVICES}
    if config.get("volumes") != volumes:
        errors.append("All five project-owned persistent volumes are required")
    networks = config.get("networks", {})
    if set(networks) != {"infra", "local"} or networks.get("infra", {}).get("internal") is not True:
        errors.append("Internal and localhost-only networks are required")
    if networks.get("local", {}).get("driver_opts") != {
        "com.docker.network.bridge.host_binding_ipv4": "127.0.0.1"
    }:
        errors.append("Host bridge must bind only to loopback")
    if config.get("secrets") != {name: {"file": f"./secrets/{name}"} for name in SECRET_NAMES}:
        errors.append("Secrets must use exact ignored local files")
    forbidden = {
        "build",
        "container_name",
        "network_mode",
        "privileged",
        "devices",
        "cap_add",
        "pid",
        "ipc",
        "env_file",
        "extends",
        "profiles",
        "entrypoint",
        "volumes_from",
    }
    targets = {
        "mysql": "/var/lib/mysql",
        "redis": "/data",
        "etcd": "/etcd",
        "seaweedfs": "/data",
        "milvus": "/var/lib/milvus",
    }
    ports = {
        "mysql": "${MYSQL_PORT:?MYSQL_PORT required}:3306",
        "redis": "${REDIS_PORT:?REDIS_PORT required}:6379",
        "seaweedfs": "${S3_PORT:?S3_PORT required}:8333",
        "milvus": "${MILVUS_PORT:?MILVUS_PORT required}:19530",
    }
    for name in SERVICES:
        service = services.get(name, {})
        image = service.get("image", "")
        if not IMAGE_PATTERN.fullmatch(image) or image != images.get(name):
            errors.append(f"Immutable derivative image mismatch: {name}")
        if service.get("pull_policy") != "never" or any(key in service for key in forbidden):
            errors.append(f"Unsafe runtime override: {name}")
        if service.get("networks") != (["infra", "local"] if name in HOST_SERVICES else ["infra"]):
            errors.append(f"Unexpected network scope: {name}")
        if service.get("volumes") != [f"{name}_data:{targets[name]}"]:
            errors.append(f"Unexpected persistent mount: {name}")
        expected_ports = [] if name == "etcd" else [f"127.0.0.1:{ports[name]}"]
        if service.get("ports", []) != expected_ports:
            errors.append(f"Host publication must remain loopback-only: {name}")
        health = service.get("healthcheck", {})
        if not health.get("test") or health.get("disable") or health.get("test") == ["NONE"]:
            errors.append(f"Real healthcheck required: {name}")
        if not all(key in health for key in ("interval", "timeout", "retries", "start_period")):
            errors.append(f"Bounded healthcheck required: {name}")
        if service.get("security_opt") != ["no-new-privileges:true"]:
            errors.append(f"Privilege guard required: {name}")
        if not service.get("mem_limit") or service.get("restart") != "unless-stopped":
            errors.append(f"Resource/restart boundary required: {name}")
        if service.get("logging") != {
            "driver": "json-file",
            "options": {"max-size": "10m", "max-file": "3"},
        }:
            errors.append(f"Bounded log rotation required: {name}")
        if health.get("test") in (["CMD", "true"], ["CMD-SHELL", "true"]):
            errors.append(f"Fake healthcheck forbidden: {name}")
    mysql = services.get("mysql", {})
    mysql_env = mysql.get("environment", {})
    if mysql.get("command") != [
        "--character-set-server=utf8mb4",
        "--collation-server=utf8mb4_0900_ai_ci",
    ]:
        errors.append("MySQL command must remain the reviewed charset contract")
    if set(mysql_env) != {
        "MYSQL_DATABASE",
        "MYSQL_USER",
        "MYSQL_ROOT_PASSWORD_FILE",
        "MYSQL_PASSWORD_FILE",
        "TZ",
    } or any(
        key in mysql_env
        for key in ("MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD", "MYSQL_ALLOW_EMPTY_PASSWORD")
    ):
        errors.append("MySQL must use only secret-file credentials")
    if services.get("redis", {}).get("command") != [
        "redis-server",
        "/run/secrets/redis_config",
    ]:
        errors.append("Redis must use the generated authenticated config")
    for name, expected in {
        "mysql": ["mysql_root_password", "mysql_password"],
        "redis": ["redis_password", "redis_config"],
    }.items():
        if services.get(name, {}).get("secrets") != expected:
            errors.append(f"Unexpected service secret contract: {name}")
    seaweed = services.get("seaweedfs", {})
    if seaweed.get("read_only") is not True:
        errors.append("SeaweedFS root filesystem must be read-only")
    for required in (
        "-volume.max=32",
        "-master.telemetry=false",
        "-s3.iam=false",
        "-s3.autoCreateBucket=false",
    ):
        if required not in seaweed.get("command", []):
            errors.append("SeaweedFS optional exposure must remain disabled")
    if services.get("milvus", {}).get("depends_on") != {
        "etcd": {"condition": "service_healthy"},
        "seaweedfs": {"condition": "service_healthy"},
    }:
        errors.append("Milvus must wait for metadata and object storage health")
    return errors


def check(root: Path = ROOT) -> list[str]:
    folder = root / "deploy/compose"
    return validate_compose(
        parse_compose((folder / "infra.compose.yml").read_text(encoding="utf-8")),
        json.loads((folder / "images.lock.json").read_text(encoding="utf-8")),
    )


def main() -> int:
    try:
        errors = check()
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        print("infra-static: FAILED (invalid inputs; no secrets logged)")
        return 1
    for error in errors:
        print(error)
    print(f"infra-static: {'FAILED' if errors else 'PASS'}; five services; locked derivatives")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
