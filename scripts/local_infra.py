"""M01 五服务本地生命周期、健康、持久化与升级演练入口。

仅操作固定 Compose project；不支持附加文件、任意服务、删卷或远程 daemon。
本地生成 secret 文件不会进入 Git，也不会在终端或异常中输出密钥值。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import storage_config
import storage_probe
import verify_infra
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "ics-v1-dev"
ENV_KEYS = {
    "INFRA_ENV",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PORT",
    "REDIS_PORT",
    "S3_PORT",
    "MILVUS_PORT",
    "INFRA_INSTANCE_ID",
}
REQUIRED_ENV_KEYS = {
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PORT",
    "REDIS_PORT",
    "INFRA_INSTANCE_ID",
}
ENV_DEFAULTS = {"INFRA_ENV": "dev", "S3_PORT": "28333", "MILVUS_PORT": "29530"}
REDIS_CONFIG = (
    "bind 0.0.0.0\nprotected-mode yes\nport 6379\ndir /data\n"
    "appendonly yes\nappendfsync everysec\nmaxmemory 256mb\n"
    "maxmemory-policy noeviction\nrequirepass {password}\n"
)


class InfraError(Exception):
    """只携带可公开的阶段说明，绝不嵌入子进程配置或密码。"""


def compose_environment(source: dict[str, str]) -> dict[str, str]:
    """拒绝可改变目标/配置的环境覆盖；数据库参数只取专用 .env。"""
    if any(
        key.startswith("COMPOSE_")
        or key in {"DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"}
        for key in source
    ):
        raise InfraError("Remove Compose/Docker target overrides before using this local tool")
    return {key: value for key, value in source.items() if key not in ENV_KEYS}


def parse_env(content: str) -> dict[str, str]:
    """开发模板只接受显式白名单键，不接受引用、展开、重复或隐藏覆盖。"""
    result = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in ENV_KEYS or key in result:
            raise InfraError("Invalid or duplicate local environment key")
        result[key] = value
    if not REQUIRED_ENV_KEYS <= set(result) or not set(result) <= ENV_KEYS:
        raise InfraError("Local environment keys do not match the reviewed template")
    result = {**ENV_DEFAULTS, **result}
    if result["INFRA_ENV"] != "dev":
        raise InfraError("The local lifecycle tool only operates the dev environment")
    if not re.fullmatch(r"[a-f0-9]{32}", result["INFRA_INSTANCE_ID"]):
        raise InfraError("Invalid local infrastructure ownership ID")
    for key in ("MYSQL_DATABASE", "MYSQL_USER"):
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,31}", result[key]) or result[key] == "root":
            raise InfraError("Invalid local database/user identifier")
    ports = []
    for key in ("MYSQL_PORT", "REDIS_PORT", "S3_PORT", "MILVUS_PORT"):
        if not result[key].isdigit() or not 1024 <= int(result[key]) <= 65535:
            raise InfraError("Invalid unprivileged local port")
        ports.append(result[key])
    if len(set(ports)) != len(ports):
        raise InfraError("Local ports must be distinct")
    return result


def ensure_local_path(path: Path, folder: Path) -> None:
    """拒绝符号链接/目录联接逃出项目，尤其不能覆盖其他项目的密钥。"""
    if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
        raise InfraError("Local configuration path escapes the project")


def initialize(root: Path = ROOT) -> None:
    """仅首次独占创建本机合成开发凭据；已有任何配置时整体拒绝轮换。"""
    folder = root / "deploy/compose"
    secret_dir = folder / "secrets"
    ensure_local_path(secret_dir, folder)
    env_file = folder / ".env"
    if env_file.exists() or secret_dir.exists():
        raise InfraError("Local credentials already exist; refusing to overwrite or rotate")
    template = (
        (folder / ".env.example")
        .read_text(encoding="utf-8")
        .replace("generated_on_init", uuid.uuid4().hex)
    )
    parse_env(template)
    passwords = {
        name: secrets.token_hex(32)
        for name in {"mysql_root_password", "mysql_password", "redis_password"}
    }
    secret_dir.mkdir(mode=0o700)
    for name, content in passwords.items():
        with (secret_dir / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content + "\n")
        # Linux 目录 0700 防止其他宿主用户读取，文件 0644 允许容器内非 root 服务读取。
        # 本地 Compose 文件型 secrets 不实现 uid/gid 重映射，不能假设 mode=0400 有效。
        (secret_dir / name).chmod(0o644)
    with (secret_dir / "redis_config").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(REDIS_CONFIG.format(password=passwords["redis_password"]))
    (secret_dir / "redis_config").chmod(0o644)
    with env_file.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(template)
    initialize_storage(root)
    # Python 3.12.4+ Windows mkdir(0o700) 创建仅当前用户/管理员可访问的 ACL。
    # 这不是加密密钥库；拥有 Docker/本机管理员权限者仍能读取文件。
    print("Local development credentials created; values withheld. Never commit secrets/ or .env.")


def initialize_storage(root: Path = ROOT) -> None:
    """Add the four storage files exactly once; supports an existing three-service M01 install."""
    folder = root / "deploy/compose"
    secret_dir = folder / "secrets"
    ensure_local_path(secret_dir, folder)
    existing = {path.name for path in secret_dir.iterdir()} if secret_dir.is_dir() else set()
    wanted = set(storage_config.SECRET_NAMES)
    if existing & wanted:
        if wanted <= existing:
            raise InfraError("Storage credentials already exist; refusing to overwrite or rotate")
        raise InfraError("Partial storage credentials found; refusing unsafe repair")
    if not verify_infra.SECRET_NAMES - wanted <= existing:
        raise InfraError("Base credentials must exist before storage initialization")
    generated = storage_config.build_secrets()
    for name, content in generated.items():
        path = secret_dir / name
        ensure_local_path(path, folder)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        path.chmod(0o644)
    print("Storage credentials created; values withheld. Existing credentials were unchanged.")


def validate_local_files(root: Path = ROOT) -> dict[str, str]:
    """执行前验证凭据强度及 Redis 配置一致性，防止手工编辑导致匿名服务。"""
    folder = root / "deploy/compose"
    ensure_local_path(folder / ".env", folder)
    config = parse_env((folder / ".env").read_text(encoding="utf-8"))
    if os.name != "nt" and (folder / "secrets").stat().st_mode & 0o077:
        raise InfraError("Secret directory must not grant group/other access")
    passwords = {}
    for name in verify_infra.SECRET_NAMES - set(storage_config.SECRET_NAMES):
        path = folder / "secrets" / name
        ensure_local_path(path, folder)
        content = path.read_text(encoding="utf-8")
        if name != "redis_config":
            if not re.fullmatch(r"[a-f0-9]{64}\n?", content):
                raise InfraError("Invalid generated secret; contents withheld")
            passwords[name] = content.strip()
    if len(set(passwords.values())) != 3:
        raise InfraError("Each service account must have a distinct generated secret")
    expected = REDIS_CONFIG.format(password=passwords["redis_password"])
    if (folder / "secrets/redis_config").read_text(encoding="utf-8") != expected:
        raise InfraError("Redis config differs from the authenticated bounded template")
    storage = {}
    for name in storage_config.SECRET_NAMES:
        path = folder / "secrets" / name
        ensure_local_path(path, folder)
        storage[name] = path.read_text(encoding="utf-8")
    storage_config.validate_secrets(storage)
    return config


def invoke(
    arguments: list[str],
    environment: dict[str, str],
    *,
    data: str | None = None,
    timeout: int = 60,
    required: bool = True,
) -> subprocess.CompletedProcess:
    """固定 argv、捕获输出；错误只报告阶段，不泄露诊断中的配置内容。"""
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        env=environment,
        input=data,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if required and result.returncode:
        raise InfraError("Docker operation failed; output withheld to protect configuration")
    return result


def local_endpoint(endpoint: str) -> bool:
    """只接受本地绝对 UNIX socket 或 localhost 命名管道，拒绝 UNC 远程主机。"""
    return bool(
        re.fullmatch(r"unix:///[^\x00\r\n]+", endpoint)
        or re.fullmatch(r"npipe:////(?:\.|localhost)/pipe/[A-Za-z0-9_.-]+", endpoint)
    )


def docker_prefix(environment: dict[str, str]) -> list[str]:
    """使用当前本机 context，但不切换用户 context；拒绝远程 Docker。"""
    context = invoke(["docker", "context", "show"], environment).stdout.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", context):
        raise InfraError("Unexpected Docker context name")
    endpoint = json.loads(
        invoke(
            [
                "docker",
                "context",
                "inspect",
                context,
                "--format",
                "{{json .Endpoints.docker.Host}}",
            ],
            environment,
        ).stdout
    )
    if not local_endpoint(endpoint):
        raise InfraError("Only a local Docker endpoint is permitted")
    prefix = ["docker", "--context", context]
    if invoke(prefix + ["info", "--format", "{{.OSType}}"], environment).stdout.strip() != "linux":
        raise InfraError("Linux containers are required")
    return prefix


def compose_prefix(docker: list[str], root: Path = ROOT) -> list[str]:
    """完整固定 Compose 文件、环境文件、目录、项目名，不接收透传参数。"""
    folder = root / "deploy/compose"
    return docker + [
        "compose",
        "--project-name",
        PROJECT,
        "--project-directory",
        str(folder),
        "--env-file",
        str(folder / ".env"),
        "--file",
        str(folder / "infra.compose.yml"),
    ]


def service_states(prefix: list[str], environment: dict[str, str]) -> list[dict]:
    """只返回安全的运行字段；兼容 Compose 的 JSON 数组与逐行 JSON 输出。"""
    output = invoke(prefix + ["ps", "--all", "--format", "json"], environment).stdout.strip()
    if not output:
        return []
    records = (
        json.loads(output)
        if output.startswith("[")
        else [json.loads(x) for x in output.splitlines()]
    )
    return [{key: row.get(key) for key in ("ID", "Service", "State", "Health")} for row in records]


def check_resources(docker: list[str], environment: dict[str, str], instance: str) -> None:
    """没有匹配实例 ID 的同名孤立卷/网络一律拒绝，不能由 Compose 默默复用。"""
    targets = {
        "volume": {f"{PROJECT}_{name}_data" for name in verify_infra.SERVICES},
        "network": {f"{PROJECT}_infra", f"{PROJECT}_local"},
    }
    for kind, expected in targets.items():
        names = invoke(
            docker + [kind, "ls", "--format", "{{.Name}}"], environment
        ).stdout.splitlines()
        for name in expected & set(names):
            labels = (
                json.loads(
                    invoke(
                        docker + [kind, "inspect", "--format", "{{json .Labels}}", name],
                        environment,
                    ).stdout
                )
                or {}
            )
            if (
                labels.get("org.ics.instance") != instance
                or labels.get("com.docker.compose.project") != PROJECT
            ):
                raise InfraError("Existing volume/network belongs to an unknown local instance")


def check_ownership(
    docker: list[str], prefix: list[str], environment: dict[str, str], instance: str
) -> None:
    """同名 project 如指向别的 Compose 工作目录，拒绝启动或停止。"""
    for row in service_states(prefix, environment):
        labels = json.loads(
            invoke(
                docker + ["inspect", "--format", "{{json .Config.Labels}}", row["ID"]],
                environment,
            ).stdout
        )
        owner = labels.get("com.docker.compose.project.working_dir", "")
        if not owner or Path(owner).resolve() != (ROOT / "deploy/compose").resolve():
            raise InfraError("Compose project name is already owned by another directory")
        if row["Service"] not in verify_infra.SERVICES:
            raise InfraError("Unexpected service in the local project; refusing mutation")
        if labels.get("org.ics.instance") != instance:
            raise InfraError("Container belongs to another local infrastructure instance")
    check_resources(docker, environment, instance)


def stop_owned(docker: list[str], environment: dict[str, str]) -> None:
    """配置丢失时仍可安全停止：先验证所有精确容器归属，再停止，不操作数据卷。"""
    ids = invoke(
        docker
        + [
            "ps",
            "--all",
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={PROJECT}",
        ],
        environment,
    ).stdout.splitlines()
    for container_id in ids:
        labels = json.loads(
            invoke(
                docker + ["inspect", "--format", "{{json .Config.Labels}}", container_id],
                environment,
            ).stdout
        )
        directory = labels.get("com.docker.compose.project.working_dir", "")
        if (
            not directory
            or Path(directory).resolve() != (ROOT / "deploy/compose").resolve()
            or labels.get("com.docker.compose.service") not in verify_infra.SERVICES
            or not re.fullmatch(r"[a-f0-9]{32}", labels.get("org.ics.instance", ""))
        ):
            raise InfraError("Refusing to stop containers not owned by this local directory")
    if ids:
        invoke(docker + ["stop", "--timeout", "30", *ids], environment, timeout=120)
    print("Only owned ics-v1-dev containers stopped; containers and volumes retained.")


def require_healthy(prefix: list[str], environment: dict[str, str]) -> None:
    rows = service_states(prefix, environment)
    if {row["Service"] for row in rows} != verify_infra.SERVICES or len(rows) != 5:
        raise InfraError("Exactly five local services must be running")
    if any(row["State"] != "running" or row["Health"] != "healthy" for row in rows):
        raise InfraError("A service is not healthy; runtime acceptance failed")


def host_probe(config: dict[str, str]) -> None:
    """从 PyCharm 所在宿主检查服务协议，不能以容器内部 healthy 替代端口可用。"""
    with socket.create_connection(
        ("127.0.0.1", int(config["MYSQL_PORT"])), timeout=3
    ) as connection:
        packet = connection.recv(256)
        if len(packet) < 8 or packet[4] != 10 or b"8.4.11" not in packet:
            raise InfraError("Local MySQL handshake/version probe failed")
    with socket.create_connection(
        ("127.0.0.1", int(config["REDIS_PORT"])), timeout=3
    ) as connection:
        connection.sendall(b"*1\r\n$4\r\nPING\r\n")
        if not connection.recv(256).startswith(b"-NOAUTH"):
            raise InfraError("Local Redis protocol/authentication probe failed")
    for key in ("S3_PORT", "MILVUS_PORT"):
        with socket.create_connection(("127.0.0.1", int(config[key])), timeout=5):
            pass
    print("PASS host loopback: MySQL/Redis/S3/Milvus protocol endpoints")


def storage_credentials(root: Path = ROOT) -> storage_config.StorageCredentials:
    """Read already-validated ignored files; callers must never print the result."""
    folder = root / "deploy/compose/secrets"
    contents = {
        name: (folder / name).read_text(encoding="utf-8") for name in storage_config.SECRET_NAMES
    }
    return storage_config.credentials(contents)


def initialize_buckets(config: dict[str, str], credentials: dict) -> None:
    """Create only the two fixed empty buckets through the admin identity."""
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        raise InfraError(
            "S3 runtime SDK is not installed; use the hash-locked infra requirements"
        ) from None
    try:
        client = boto3.client(
            "s3",
            endpoint_url=f"http://127.0.0.1:{config['S3_PORT']}",
            region_name=storage_config.REGION,
            aws_access_key_id=credentials["admin"]["access_key"],
            aws_secret_access_key=credentials["admin"]["secret_key"],
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        existing = {item["Name"] for item in client.list_buckets().get("Buckets", [])}
        for bucket in (storage_config.KNOWLEDGE_BUCKET, storage_config.MILVUS_BUCKET):
            if bucket not in existing:
                client.create_bucket(Bucket=bucket)
    except (BotoCoreError, ClientError, KeyError, OSError, TypeError, ValueError):
        raise InfraError("Fixed S3 bucket initialization failed; details withheld") from None
    print("PASS object storage initialization: two fixed buckets present")


def prepare_nonroot_volumes(
    docker: list[str], prefix: list[str], environment: dict[str, str], instance: str
) -> None:
    """Create owned volumes and grant only etcd/Seaweed service UID access; never delete data."""
    invoke(prefix + ["create", "etcd", "seaweedfs"], environment, timeout=180)
    check_resources(docker, environment, instance)
    invoke(prefix + ["stop", "etcd", "seaweedfs"], environment, timeout=120)
    helper = "ics-seaweedfs:4.45-m01-security.1@sha256:dfac2e817ad5b9b2c6ee725127905f3893787089690318772c942f4239989c00"
    for volume, initialize_dirs in (
        (f"{PROJECT}_etcd_data", False),
        (f"{PROJECT}_seaweedfs_data", True),
    ):
        script = (
            "mkdir -p /target/master /target/filerldb2; chown -R 1000:1000 /target"
            if initialize_dirs
            else "chown -R 1000:1000 /target"
        )
        invoke(
            docker
            + [
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--user",
                "0:0",
                "--cap-drop=ALL",
                "--cap-add=CHOWN",
                "--cap-add=DAC_OVERRIDE",
                "--security-opt=no-new-privileges",
                "--entrypoint",
                "/bin/busybox",
                "--mount",
                f"type=volume,src={volume},dst=/target",
                helper,
                "sh",
                "-ec",
                script,
            ],
            environment,
            timeout=300,
        )


def start_all(
    docker: list[str], prefix: list[str], environment: dict[str, str], config: dict[str, str]
) -> None:
    prepare_nonroot_volumes(docker, prefix, environment, config["INFRA_INSTANCE_ID"])
    invoke(
        prefix
        + [
            "up",
            "--detach",
            "--wait",
            "--wait-timeout",
            "300",
            "mysql",
            "redis",
            "etcd",
            "seaweedfs",
        ],
        environment,
        timeout=600,
    )
    initialize_buckets(config, storage_credentials())
    invoke(
        prefix + ["up", "--detach", "--wait", "--wait-timeout", "360", "milvus"],
        environment,
        timeout=600,
    )
    require_healthy(prefix, environment)
    host_probe(config)


def persistence_cycle(
    docker: list[str],
    prefix: list[str],
    environment: dict[str, str],
    config: dict[str, str],
    *,
    recreate: bool,
) -> None:
    """Write owned sentinels, stop/recreate without deleting volumes, verify, then clean only sentinels."""
    require_healthy(prefix, environment)
    marker = uuid.uuid4().hex
    credentials = storage_credentials()
    endpoint = f"http://127.0.0.1:{config['S3_PORT']}"
    milvus_uri = f"http://127.0.0.1:{config['MILVUS_PORT']}"
    manifest = storage_probe.persist_prepare(
        endpoint, credentials["knowledge"], milvus_uri, credentials["milvus_token"]
    )
    mysql = prefix + [
        "exec",
        "-T",
        "mysql",
        "sh",
        "-ec",
        'export MYSQL_PWD="$(cat /run/secrets/mysql_password)"; exec mysql --protocol=TCP -h127.0.0.1 -u"$MYSQL_USER" -D"$MYSQL_DATABASE" -N -B',
    ]
    sql = f"CREATE TABLE IF NOT EXISTS _m01_persistence (id CHAR(32) PRIMARY KEY); INSERT INTO _m01_persistence VALUES ('{marker}');\n"
    invoke(mysql, environment, data=sql)
    redis = prefix + [
        "exec",
        "-T",
        "redis",
        "sh",
        "-ec",
        'export REDISCLI_AUTH="$(cat /run/secrets/redis_password)"; exec redis-cli --raw',
    ]
    invoke(redis, environment, data=f"SET m01:persist:{marker} synthetic-only\nSAVE\n")
    etcd = prefix + [
        "exec",
        "-T",
        "etcd",
        "/usr/local/bin/etcdctl",
        "--endpoints=http://127.0.0.1:2379",
    ]
    invoke(etcd + ["put", f"/ics/m01/persist/{marker}", "synthetic-only"], environment)
    stop_owned(docker, environment)
    if recreate:
        invoke(
            prefix + ["up", "--detach", "--force-recreate", "--wait", "--wait-timeout", "420"],
            environment,
            timeout=720,
        )
    else:
        start_all(docker, prefix, environment, config)
    require_healthy(prefix, environment)
    if (
        invoke(
            mysql, environment, data=f"SELECT COUNT(*) FROM _m01_persistence WHERE id='{marker}';\n"
        ).stdout.strip()
        != "1"
    ):
        raise InfraError("MySQL persistence verification failed")
    if (
        invoke(redis, environment, data=f"GET m01:persist:{marker}\n").stdout.strip()
        != "synthetic-only"
    ):
        raise InfraError("Redis persistence verification failed")
    if (
        invoke(
            etcd + ["get", f"/ics/m01/persist/{marker}", "--print-value-only"], environment
        ).stdout.strip()
        != "synthetic-only"
    ):
        raise InfraError("etcd persistence verification failed")
    storage_probe.persist_verify(
        endpoint, credentials["knowledge"], milvus_uri, credentials["milvus_token"], manifest
    )
    invoke(mysql, environment, data=f"DELETE FROM _m01_persistence WHERE id='{marker}';\n")
    invoke(redis, environment, data=f"DEL m01:persist:{marker}\n")
    invoke(etcd + ["del", f"/ics/m01/persist/{marker}"], environment)
    storage_probe.persist_cleanup(
        endpoint, credentials["knowledge"], milvus_uri, credentials["milvus_token"], manifest
    )
    print(
        f"PASS {'force-recreate upgrade' if recreate else 'stop/start'} persistence for all five services"
    )


def smoke(prefix: list[str], environment: dict[str, str]) -> None:
    """仅在新项目写唯一合成探针，并删除本次探针；不接触业务/原 KF 数据。"""
    require_healthy(prefix, environment)
    probe = uuid.uuid4().hex
    mysql = prefix + [
        "exec",
        "-T",
        "mysql",
        "sh",
        "-ec",
        (
            'export MYSQL_PWD="$(cat /run/secrets/mysql_password)"; '
            'exec mysql --protocol=TCP -h127.0.0.1 -u"$MYSQL_USER" -D"$MYSQL_DATABASE" -N -B'
        ),
    ]
    sql = (
        "CREATE TABLE IF NOT EXISTS _m01_infra_smoke (id CHAR(32) PRIMARY KEY, value VARCHAR(64));\n"
        f"INSERT INTO _m01_infra_smoke VALUES ('{probe}', 'synthetic-only');\n"
        f"SELECT value FROM _m01_infra_smoke WHERE id='{probe}';\n"
        f"DELETE FROM _m01_infra_smoke WHERE id='{probe}';\n"
    )
    if invoke(mysql, environment, data=sql).stdout.strip() != "synthetic-only":
        raise InfraError("MySQL authenticated write/read probe failed")
    denied = invoke(
        prefix
        + [
            "exec",
            "-T",
            "mysql",
            "sh",
            "-ec",
            'unset MYSQL_PWD; exec mysql --protocol=TCP -h127.0.0.1 -u"$MYSQL_USER" -Nse "SELECT 1"',
        ],
        environment,
        required=False,
    )
    if denied.returncode == 0 or "Access denied" not in denied.stderr:
        raise InfraError("MySQL unauthenticated access was not rejected as expected")
    print("PASS MySQL: application account write/read; missing credential denied")
    redis = prefix + [
        "exec",
        "-T",
        "redis",
        "sh",
        "-ec",
        'export REDISCLI_AUTH="$(cat /run/secrets/redis_password)"; exec redis-cli --raw',
    ]
    redis_commands = f"SET m01:probe:{probe} synthetic-only EX 60\nGET m01:probe:{probe}\nDEL m01:probe:{probe}\n"
    if invoke(redis, environment, data=redis_commands).stdout.split() != [
        "OK",
        "synthetic-only",
        "1",
    ]:
        raise InfraError("Redis authenticated write/read probe failed")
    denied = invoke(prefix + ["exec", "-T", "redis", "redis-cli", "--raw", "ping"], environment)
    if "NOAUTH" not in denied.stdout:
        raise InfraError("Redis unauthenticated access was not rejected")
    print("PASS Redis: authenticated write/read; anonymous access denied")
    etcd = prefix + [
        "exec",
        "-T",
        "etcd",
        "etcdctl",
        "--endpoints=http://127.0.0.1:2379",
    ]
    key = f"/ics/m01/probe/{probe}"
    invoke(etcd + ["put", key, "synthetic-only"], environment)
    value = invoke(etcd + ["get", key, "--print-value-only"], environment).stdout.strip()
    invoke(etcd + ["del", key], environment)
    if value != "synthetic-only":
        raise InfraError("etcd internal-network write/read probe failed")
    print("PASS etcd: internal endpoint health and synthetic write/read")
    config = validate_local_files()
    credentials = storage_credentials()
    try:
        storage_result = storage_probe.run_checks(
            f"http://127.0.0.1:{config['S3_PORT']}",
            credentials["admin"],
            credentials["knowledge"],
            f"http://127.0.0.1:{config['MILVUS_PORT']}",
            credentials["milvus_token"],
        )
    except storage_probe.ProbeFailure as exc:
        raise InfraError(f"Storage contract failed at {exc}") from None
    print(f"PASS S3/Milvus synthetic contract: {len(storage_result)} checks")
    print("M01 five-service smoke PASS; 93 business cases remain NOT_RUN")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "init",
            "init-storage",
            "config",
            "up",
            "status",
            "health",
            "smoke",
            "restart-test",
            "upgrade",
            "stop",
        ],
    )
    action = parser.parse_args().action
    try:
        environment = compose_environment(dict(os.environ))
        if action == "stop":
            stop_owned(docker_prefix(environment), environment)
            return 0
        if verify_infra.check():
            raise InfraError("Static Compose boundary check failed")
        if action == "init":
            initialize()
            return 0
        if action == "init-storage":
            initialize_storage()
            return 0
        config = validate_local_files()
        # Compose receives only values parsed from the dedicated local file plus
        # reviewed defaults, never same-named values inherited from the shell.
        environment = {**environment, **config}
        docker = docker_prefix(environment)
        prefix = compose_prefix(docker)
        invoke(prefix + ["config", "--quiet"], environment)
        check_ownership(docker, prefix, environment, config["INFRA_INSTANCE_ID"])
        if action == "up":
            if not service_states(prefix, environment):
                for key in ("MYSQL_PORT", "REDIS_PORT", "S3_PORT", "MILVUS_PORT"):
                    with socket.socket() as check_socket:
                        check_socket.bind(("127.0.0.1", int(config[key])))
            start_all(docker, prefix, environment, config)
            print("Five M01 services healthy; object buckets initialized.")
        elif action in {"health", "smoke"}:
            host_probe(config)
            smoke(prefix, environment)
        elif action == "restart-test":
            persistence_cycle(docker, prefix, environment, config, recreate=False)
        elif action == "upgrade":
            persistence_cycle(docker, prefix, environment, config, recreate=True)
        elif action == "status":
            print(json.dumps(service_states(prefix, environment), ensure_ascii=False, indent=2))
        else:
            print("Compose and local credentials valid; no configuration values printed.")
    except (
        InfraError,
        storage_probe.ProbeFailure,
        OSError,
        ValueError,
        TypeError,
        subprocess.SubprocessError,
        yaml.YAMLError,
    ) as exc:
        detail = (
            str(exc)
            if isinstance(exc, (InfraError, storage_probe.ProbeFailure))
            else type(exc).__name__
        )
        print(f"local-infra FAILED: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
