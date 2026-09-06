"""验证 M01.1 可执行配置边界；只解析配置，不读取密钥或启动 Docker。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {"mysql", "redis", "etcd"}
SECRET_NAMES = {"mysql_root_password", "mysql_password", "redis_password", "redis_config"}
IMAGE_PATTERN = re.compile(r".+:[A-Za-z0-9_.-]+@sha256:[a-f0-9]{64}")
INSTANCE_LABELS = {"org.ics.instance": "${INFRA_INSTANCE_ID:?INFRA_INSTANCE_ID required}"}
COMMANDS = {
    "mysql": ["--character-set-server=utf8mb4", "--collation-server=utf8mb4_0900_ai_ci"],
    "redis": ["redis-server", "/run/secrets/redis_config"],
    "etcd": [
        "etcd",
        "--name=ics-etcd",
        "--data-dir=/etcd",
        "--advertise-client-urls=http://etcd:2379",
        "--listen-client-urls=http://0.0.0.0:2379",
        "--listen-peer-urls=http://127.0.0.1:2380",
        "--initial-advertise-peer-urls=http://127.0.0.1:2380",
        "--initial-cluster=ics-etcd=http://127.0.0.1:2380",
    ],
}
HEALTH_TESTS = {
    "mysql": [
        "CMD-SHELL",
        'MYSQL_PWD="$$(cat /run/secrets/mysql_root_password)" mysql --protocol=TCP -h127.0.0.1 -uroot -Nse "SELECT 1" | grep -qx 1',
    ],
    "redis": [
        "CMD-SHELL",
        'REDISCLI_AUTH="$$(cat /run/secrets/redis_password)" redis-cli --raw ping | grep -qx PONG',
    ],
    "etcd": ["CMD", "etcdctl", "--endpoints=http://127.0.0.1:2379", "endpoint", "health"],
}


class ComposeLoader(yaml.SafeLoader):
    """允许受控 anchor/merge，但拒绝重复显式键，避免 YAML 静默覆盖。"""

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
    """只接受数据映射，不能加载任意 Python 对象。"""
    result = yaml.load(content, Loader=ComposeLoader)
    if not isinstance(result, dict):
        raise ValueError("Compose must be a mapping")
    return result


def validate_compose(config: dict, lock: dict) -> list[str]:
    """固定三服务开发子集；修改边界必须同时更新决策、守卫与负向测试。"""
    errors = []
    services = config.get("services", {})
    if config.get("name") != "ics-v1-dev" or set(services) != SERVICES:
        errors.append("Only the isolated three-service M01.1 subset is executable")
    if any(key in config for key in ("include", "configs", "profiles")):
        errors.append("Unexpected additional Compose inputs")
    if lock.get("schema_version") != 1 or set(lock.get("images", {})) != SERVICES:
        errors.append("Image lock does not match executable service scope")
    expected_networks = {
        "infra": {"internal": True, "labels": INSTANCE_LABELS},
        "local": {
            "driver": "bridge",
            "driver_opts": {"com.docker.network.bridge.host_binding_ipv4": "127.0.0.1"},
            "labels": INSTANCE_LABELS,
        },
    }
    if config.get("networks") != expected_networks:
        errors.append("Only project-owned internal and localhost-access networks are allowed")
    expected_volumes = {f"{name}_data": {"labels": INSTANCE_LABELS} for name in SERVICES}
    if config.get("volumes") != expected_volumes:
        errors.append("Volumes must be project-scoped, not external or explicitly named")
    expected_secrets = {name: {"file": f"./secrets/{name}"} for name in SECRET_NAMES}
    if config.get("secrets") != expected_secrets:
        errors.append("Secrets must come from ignored local files")
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
    for name, service in services.items():
        image = service.get("image", "")
        if not IMAGE_PATTERN.fullmatch(image) or image != lock.get("images", {}).get(name):
            errors.append(f"Immutable image mismatch: {name}")
        if ":latest@" in image or any(key in service for key in forbidden):
            errors.append(f"Unsafe runtime override: {name}")
        if service.get("networks") != (["infra"] if name == "etcd" else ["infra", "local"]):
            errors.append(f"Unexpected network: {name}")
        if service.get("labels") != INSTANCE_LABELS:
            errors.append(f"Missing local instance ownership: {name}")
        if service.get("command") != COMMANDS.get(name):
            errors.append(f"Unexpected service command: {name}")
        if service.get("security_opt") != ["no-new-privileges:true"]:
            errors.append(f"Missing privilege guard: {name}")
        if service.get("volumes") != [
            f"{name}_data:{ {'mysql': '/var/lib/mysql', 'redis': '/data', 'etcd': '/etcd'}.get(name, '') }"
        ]:
            errors.append(f"Unexpected data mount: {name}")
        expected_ports = {
            "mysql": ["127.0.0.1:${MYSQL_PORT:?MYSQL_PORT required}:3306"],
            "redis": ["127.0.0.1:${REDIS_PORT:?REDIS_PORT required}:6379"],
            "etcd": [],
        }
        if service.get("ports", []) != expected_ports.get(name):
            errors.append(f"Host publication must remain loopback-only: {name}")
        health = service.get("healthcheck", {})
        if health.get("test") != HEALTH_TESTS.get(name):
            errors.append(f"Authenticated healthcheck contract changed: {name}")
        expected_health = {
            "test": HEALTH_TESTS.get(name),
            "interval": "10s",
            "timeout": "5s",
            "retries": 18 if name == "mysql" else 6,
            "start_period": "60s" if name == "mysql" else "10s",
        }
        if health != expected_health:
            errors.append(f"Healthcheck timing/behavior changed: {name}")
        if not health.get("test") or health.get("disable") or health.get("test") == ["NONE"]:
            errors.append(f"Real healthcheck required: {name}")
        for key in ("interval", "timeout", "retries", "start_period"):
            if key not in health:
                errors.append(f"Bounded healthcheck required: {name}")
        if not service.get("mem_limit") or service.get("logging", {}).get("driver") != "json-file":
            errors.append(f"Resource/logging bounds required: {name}")
        if service.get("restart") != "unless-stopped":
            errors.append(f"Unexpected restart behavior: {name}")
        if service.get("logging") != {
            "driver": "json-file",
            "options": {"max-size": "10m", "max-file": "3"},
        }:
            errors.append(f"Bounded log rotation required: {name}")
    mysql = services.get("mysql", {})
    mysql_env = mysql.get("environment", {})
    if mysql_env != {
        "MYSQL_DATABASE": "${MYSQL_DATABASE:?Run python scripts/local_infra.py init first}",
        "MYSQL_USER": "${MYSQL_USER:?Run python scripts/local_infra.py init first}",
        "MYSQL_ROOT_PASSWORD_FILE": "/run/secrets/mysql_root_password",
        "MYSQL_PASSWORD_FILE": "/run/secrets/mysql_password",
        "TZ": "UTC",
    }:
        errors.append("MySQL environment must remain the reviewed secret-file contract")
    if services.get("redis", {}).get("environment", {}):
        errors.append("Unexpected Redis environment override")
    if services.get("etcd", {}).get("environment") != {
        "ETCD_AUTO_COMPACTION_MODE": "revision",
        "ETCD_AUTO_COMPACTION_RETENTION": "1000",
        "ETCD_QUOTA_BACKEND_BYTES": "4294967296",
        "ETCD_SNAPSHOT_COUNT": "50000",
    }:
        errors.append("Unexpected etcd environment override")
    if mysql_env.get("MYSQL_ROOT_PASSWORD_FILE") != "/run/secrets/mysql_root_password":
        errors.append("MySQL root password must be a secret file")
    if mysql_env.get("MYSQL_PASSWORD_FILE") != "/run/secrets/mysql_password":
        errors.append("MySQL application password must be a secret file")
    if any(
        key in mysql_env
        for key in (
            "MYSQL_ROOT_PASSWORD",
            "MYSQL_PASSWORD",
            "MYSQL_ALLOW_EMPTY_PASSWORD",
            "MYSQL_RANDOM_ROOT_PASSWORD",
            "MYSQL_ROOT_HOST",
        )
    ):
        errors.append("MySQL password/default-root override forbidden")
    if services.get("redis", {}).get("command") != ["redis-server", "/run/secrets/redis_config"]:
        errors.append("Redis must read the generated authenticated config")
    for name, expected in {
        "mysql": ["mysql_root_password", "mysql_password"],
        "redis": ["redis_password", "redis_config"],
        "etcd": [],
    }.items():
        if services.get(name, {}).get("secrets", []) != expected:
            errors.append(f"Unexpected service secrets: {name}")
    return errors


def check(root: Path = ROOT) -> list[str]:
    """对仓库内的配置与锁文件执行同一组可复现检查。"""
    folder = root / "deploy/compose"
    config = parse_compose((folder / "infra.compose.yml").read_text(encoding="utf-8"))
    lock = json.loads((folder / "images.lock.json").read_text(encoding="utf-8"))
    return validate_compose(config, lock)


def main() -> int:
    try:
        errors = check()
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        print("infra-static: FAILED (invalid inputs; no secrets logged)")
        return 1
    for error in errors:
        print(error)
    print(f"infra-static: {'FAILED' if errors else 'PASS'}; 3 services; S3/Milvus DEFERRED")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
