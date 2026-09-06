"""M01.1 三服务开发验证入口，不是 M01.4 的完整部署/升级工具。

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

import yaml

import verify_infra

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "ics-v1-dev"
ENV_KEYS = {"MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PORT", "REDIS_PORT", "INFRA_INSTANCE_ID"}
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
    """开发模板只接受五个显式键，不接受引用、展开、重复或隐藏覆盖。"""
    result = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in ENV_KEYS or key in result:
            raise InfraError("Invalid or duplicate local environment key")
        result[key] = value
    if set(result) != ENV_KEYS:
        raise InfraError("Local environment must contain exactly the five template keys")
    if not re.fullmatch(r"[a-f0-9]{32}", result["INFRA_INSTANCE_ID"]):
        raise InfraError("Invalid local infrastructure ownership ID")
    for key in ("MYSQL_DATABASE", "MYSQL_USER"):
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,31}", result[key]) or result[key] == "root":
            raise InfraError("Invalid local database/user identifier")
    ports = []
    for key in ("MYSQL_PORT", "REDIS_PORT"):
        if not result[key].isdigit() or not 1024 <= int(result[key]) <= 65535:
            raise InfraError("Invalid unprivileged local port")
        ports.append(result[key])
    if ports[0] == ports[1]:
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
        name: secrets.token_hex(32) for name in verify_infra.SECRET_NAMES - {"redis_config"}
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
    # Python 3.12.4+ Windows mkdir(0o700) 创建仅当前用户/管理员可访问的 ACL。
    # 这不是加密密钥库；拥有 Docker/本机管理员权限者仍能读取文件。
    print("Local development credentials created; values withheld. Never commit secrets/ or .env.")


def validate_local_files(root: Path = ROOT) -> dict[str, str]:
    """执行前验证凭据强度及 Redis 配置一致性，防止手工编辑导致匿名服务。"""
    folder = root / "deploy/compose"
    ensure_local_path(folder / ".env", folder)
    config = parse_env((folder / ".env").read_text(encoding="utf-8"))
    if os.name != "nt" and (folder / "secrets").stat().st_mode & 0o077:
        raise InfraError("Secret directory must not grant group/other access")
    passwords = {}
    for name in verify_infra.SECRET_NAMES:
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
        + ["ps", "--all", "--quiet", "--filter", f"label=com.docker.compose.project={PROJECT}"],
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
        invoke(docker + ["stop", "--time", "30", *ids], environment, timeout=120)
    print("Only owned ics-v1-dev containers stopped; containers and volumes retained.")


def require_healthy(prefix: list[str], environment: dict[str, str]) -> None:
    rows = service_states(prefix, environment)
    if {row["Service"] for row in rows} != verify_infra.SERVICES or len(rows) != 3:
        raise InfraError("Exactly three local services must be running")
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
    print("PASS host loopback: MySQL handshake and Redis anonymous rejection")


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
        'export MYSQL_PWD="$(cat /run/secrets/mysql_password)"; '
        'exec mysql --protocol=TCP -h127.0.0.1 -u"$MYSQL_USER" -D"$MYSQL_DATABASE" -N -B',
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
    etcd = prefix + ["exec", "-T", "etcd", "etcdctl", "--endpoints=http://127.0.0.1:2379"]
    key = f"/ics/m01/probe/{probe}"
    invoke(etcd + ["put", key, "synthetic-only"], environment)
    value = invoke(etcd + ["get", key, "--print-value-only"], environment).stdout.strip()
    invoke(etcd + ["del", key], environment)
    if value != "synthetic-only":
        raise InfraError("etcd internal-network write/read probe failed")
    print("PASS etcd: internal endpoint health and synthetic write/read")
    print("Infrastructure subset PASS; S3/Milvus NOT_RUN; 93 business cases NOT_RUN")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "config", "up", "status", "smoke", "stop"])
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
        config = validate_local_files()
        docker = docker_prefix(environment)
        prefix = compose_prefix(docker)
        invoke(prefix + ["config", "--quiet"], environment)
        check_ownership(docker, prefix, environment, config["INFRA_INSTANCE_ID"])
        if action == "up":
            if not service_states(prefix, environment):
                for key in ("MYSQL_PORT", "REDIS_PORT"):
                    with socket.socket() as check_socket:
                        check_socket.bind(("127.0.0.1", int(config[key])))
            invoke(
                prefix
                + ["up", "--detach", "--wait", "--wait-timeout", "240", "mysql", "redis", "etcd"],
                environment,
                timeout=600,
            )
            require_healthy(prefix, environment)
            host_probe(config)
            print("Three services healthy. Object storage and Milvus were NOT started.")
        elif action == "smoke":
            host_probe(config)
            smoke(prefix, environment)
        elif action == "status":
            print(json.dumps(service_states(prefix, environment), ensure_ascii=False, indent=2))
        else:
            print("Compose and local credentials valid; no configuration values printed.")
    except (
        InfraError,
        OSError,
        ValueError,
        TypeError,
        subprocess.SubprocessError,
        yaml.YAMLError,
    ) as exc:
        detail = str(exc) if isinstance(exc, InfraError) else type(exc).__name__
        print(f"local-infra FAILED: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
