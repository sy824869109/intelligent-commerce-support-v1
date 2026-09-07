"""M01 固定对象存储/Milvus 配置：生成、校验与取值均不进行文件或网络 I/O。

仅用于新平台独占的合成开发环境；不读取或修改原 KF。调用方负责独占写入
被 Git 忽略的 secrets 目录、访问控制及容器启动，不可打印返回值。

SeaweedFS 4.45: weed/command/scaffold/security.toml、weed/s3api/auth_credentials.go。
Milvus 2.6.23: configs/milvus.yaml、pkg/util/paramtable/base_table.go。
milvus_config 挂载 /milvus/configs/user.yaml，保留镜像内原始 milvus.yaml 默认值。
seaweed_security_config 挂载 /etc/seaweedfs/security.toml，单进程各组件共享。
JWT 自动由组件读取并用于内部签名；不需要另传签名 flag。不启用不适用于
Filer 的 jwt.signing.read，不把内部 JWT 配置误称为 gRPC mTLS 或静态加密。
"""

from __future__ import annotations

import json
import re
import secrets
import tomllib
from typing import TypedDict

import yaml

SECRET_NAMES = frozenset(
    {"seaweed_s3_config", "seaweed_security_config", "milvus_config", "milvus_root_password"}
)
KNOWLEDGE_BUCKET = "ics-knowledge"
MILVUS_BUCKET = "ics-milvus"
MILVUS_ROOT_PATH = "v1"
ETCD_ROOT_PATH = "ics-v1-milvus"
REGION = "us-east-1"
IDENTITY_PREFIXES = {"admin": "ICSA", "knowledge": "ICSK", "milvus": "ICSM"}


class StorageConfigError(ValueError):
    """异常仅包含公开阶段名称，不包含配置片段、密钥或原始解析异常。"""


class S3Credential(TypedDict):
    access_key: str
    secret_key: str


class StorageCredentials(TypedDict):
    admin: S3Credential
    knowledge: S3Credential
    milvus: S3Credential
    milvus_token: str
    milvus_root_password: str


def _secret_valid(value: object) -> bool:
    """检查生成格式及明显重复弱值；不声称能从字符串证明密码学熵。"""
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        return False
    if len(set(value)) < 8:
        return False
    return not any(value == value[:size] * (64 // size) for size in (1, 2, 4, 8, 16, 32))


def _new_secret() -> str:
    while True:
        value = secrets.token_hex(32)
        if _secret_valid(value):
            return value


def _s3_document(accounts: dict[str, S3Credential]) -> dict:
    identities = []
    for name in IDENTITY_PREFIXES:
        bucket = KNOWLEDGE_BUCKET if name == "knowledge" else MILVUS_BUCKET
        actions = (
            ["Admin"]
            if name == "admin"
            else [f"Read:{bucket}", f"Write:{bucket}", f"List:{bucket}"]
        )
        identities.append(
            {
                "name": name,
                "credentials": [
                    {
                        "accessKey": accounts[name]["access_key"],
                        "secretKey": accounts[name]["secret_key"],
                    }
                ],
                "actions": actions,
            }
        )
    return {"identities": identities}


def _s3_text(accounts: dict[str, S3Credential]) -> str:
    return json.dumps(_s3_document(accounts), ensure_ascii=True, indent=2) + "\n"


def _security_text(keys: dict[str, str]) -> str:
    return (
        "# SeaweedFS 4.45: internal write/read guards, not gRPC mTLS.\n"
        "# Do not add jwt.signing.read: unsupported with this Filer path.\n"
        "[access]\nui = false\n\n"
        "[filer.expose_directory_metadata]\nenabled = false\n\n"
        "[jwt.signing]\n"
        f'key = "{keys["volume_write"]}"\nexpires_after_seconds = 10\n\n'
        "[jwt.filer_signing]\n"
        f'key = "{keys["filer_write"]}"\nexpires_after_seconds = 10\n\n'
        "[jwt.filer_signing.read]\n"
        f'key = "{keys["filer_read"]}"\nexpires_after_seconds = 10\n'
    )


def _milvus_text(account: S3Credential, root_password: str) -> str:
    # Only the canonical generated values enter YAML; no arbitrary interpolation.
    return (
        "# Milvus 2.6.23 user.yaml overlay; S3 provider name remains minio.\n"
        "# Local synthetic development only; HTTP stays on isolated/local networks.\n"
        "etcd:\n  endpoints:\n    - etcd:2379\n"
        f"  rootPath: {ETCD_ROOT_PATH}\n"
        "localStorage:\n  path: /var/lib/milvus/data/\n"
        "mq:\n  type: rocksmq\n"
        "rocksmq:\n  path: /var/lib/milvus/rdb_data\n"
        "minio:\n  address: seaweedfs\n  port: 8333\n"
        f'  accessKeyID: "{account["access_key"]}"\n'
        f'  secretAccessKey: "{account["secret_key"]}"\n'
        f"  bucketName: {MILVUS_BUCKET}\n  rootPath: {MILVUS_ROOT_PATH}\n"
        "  useSSL: false\n  useIAM: false\n  cloudProvider: aws\n"
        f"  region: {REGION}\n  useVirtualHost: false\n  requestTimeoutMs: 10000\n"
        "common:\n  storageType: remote\n  security:\n"
        "    authorizationEnabled: true\n"
        f'    defaultRootPassword: "{root_password}"\n'
        "    rootShouldBindRole: false\n    enablePublicPrivilege: false\n"
    )


def build_secrets() -> dict[str, str]:
    """返回四个新存储 secret 的文件名/内容；每次调用生成独立随机值。"""
    accounts = {
        name: S3Credential(
            access_key=prefix + secrets.token_hex(8).upper(), secret_key=_new_secret()
        )
        for name, prefix in IDENTITY_PREFIXES.items()
    }
    keys = {name: _new_secret() for name in ("volume_write", "filer_write", "filer_read")}
    root_password = _new_secret()
    result = {
        "seaweed_s3_config": _s3_text(accounts),
        "seaweed_security_config": _security_text(keys),
        "milvus_config": _milvus_text(accounts["milvus"], root_password),
        "milvus_root_password": root_password + "\n",
    }
    validate_secrets(result)
    return result


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise StorageConfigError("Duplicate storage identity configuration key")
        result[name] = value
    return result


def _parse(contents: dict[str, str]) -> tuple[dict[str, S3Credential], dict[str, str], str]:
    """读取受控值，任何解析错误均不回显可能包含密钥的输入。"""
    try:
        if not isinstance(contents, dict) or set(contents) != SECRET_NAMES:
            raise StorageConfigError("Storage secrets must match exactly the four-file contract")
        if any(not isinstance(value, str) or len(value) > 65536 for value in contents.values()):
            raise StorageConfigError("Invalid storage secret content type or size")
        document = json.loads(contents["seaweed_s3_config"], object_pairs_hook=_unique_pairs)
        identities = document["identities"]
        if len(identities) != 3 or [item["name"] for item in identities] != list(IDENTITY_PREFIXES):
            raise StorageConfigError("Unexpected storage identities or identity ordering")
        accounts = {}
        for item in identities:
            if len(item["credentials"]) != 1:
                raise StorageConfigError("Exactly one credential per storage identity is required")
            pair = item["credentials"][0]
            accounts[item["name"]] = S3Credential(
                access_key=pair["accessKey"], secret_key=pair["secretKey"]
            )
        security = tomllib.loads(contents["seaweed_security_config"])
        keys = {
            "volume_write": security["jwt"]["signing"]["key"],
            "filer_write": security["jwt"]["filer_signing"]["key"],
            "filer_read": security["jwt"]["filer_signing"]["read"]["key"],
        }
        root_password = contents["milvus_root_password"].removesuffix("\n")
        return accounts, keys, root_password
    except StorageConfigError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
        raise StorageConfigError("Storage secret parsing failed; content withheld") from None


def validate_secrets(contents: dict[str, str]) -> None:
    """拒绝权限扩大、凭据复用、弱值及固定配置漂移，不启动任何服务。"""
    accounts, keys, root_password = _parse(contents)
    values = [account["secret_key"] for account in accounts.values()]
    values += list(keys.values()) + [root_password]
    if not all(_secret_valid(value) for value in values) or len(set(values)) != len(values):
        raise StorageConfigError("Storage credentials must be strong and independently generated")
    for name, account in accounts.items():
        access_key = account["access_key"]
        if (
            not isinstance(access_key, str)
            or re.fullmatch(IDENTITY_PREFIXES[name] + r"[A-F0-9]{16}", access_key) is None
        ):
            raise StorageConfigError("Invalid generated storage access key")
    expected = {
        "seaweed_s3_config": _s3_text(accounts),
        "seaweed_security_config": _security_text(keys),
        "milvus_config": _milvus_text(accounts["milvus"], root_password),
        "milvus_root_password": root_password + "\n",
    }
    normalized = dict(contents)
    normalized["milvus_config"] = normalized["milvus_config"].replace(
        "# Milvus 2.5.15 user.yaml overlay;", "# Milvus 2.6.23 user.yaml overlay;", 1
    )
    if normalized != expected:
        raise StorageConfigError("Storage configuration differs from the restricted fixed template")
    # Parse the generated overlay too: a future template syntax error must fail locally.
    try:
        milvus = yaml.safe_load(contents["milvus_config"])
    except yaml.YAMLError:
        raise StorageConfigError("Milvus configuration syntax check failed") from None
    if milvus["common"]["security"]["defaultRootPassword"] != root_password:
        raise StorageConfigError("Milvus initialization credential mismatch")


def credentials(contents: dict[str, str]) -> StorageCredentials:
    """返回已完整校验的凭据；调用方只可用于受控 SDK 调用，不可记录返回值。"""
    validate_secrets(contents)
    accounts, _, root_password = _parse(contents)
    return StorageCredentials(
        admin=accounts["admin"],
        knowledge=accounts["knowledge"],
        milvus=accounts["milvus"],
        milvus_token=f"root:{root_password}",
        milvus_root_password=root_password,
    )
