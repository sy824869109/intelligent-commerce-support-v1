"""Load the reviewed dev/test/prod infrastructure profile without reading secrets."""

from __future__ import annotations
import argparse
import ipaddress
import json
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = {"dev", "test", "prod"}
SERVICES = {"mysql", "redis", "s3", "milvus"}
CONTRACTS = {
    "dev": "local_ignored_files",
    "test": "ci_ephemeral_secret_files",
    "prod": "external_secret_files",
}
DATA_CLASSES = {
    "dev": "synthetic_development_only",
    "test": "synthetic_test_only",
    "prod": "approved_business_data",
}


class SettingsError(ValueError):
    pass


def validate(profile: object, selected: str) -> dict:
    if selected not in ENVIRONMENTS or not isinstance(profile, dict):
        raise SettingsError("Unknown or invalid infrastructure profile")
    if set(profile) != {
        "schema_version",
        "environment",
        "hosts",
        "ports",
        "tls_required",
        "secret_contract",
        "data_class",
    }:
        raise SettingsError("Infrastructure profile keys changed")
    if profile["schema_version"] != 1 or profile["environment"] != selected:
        raise SettingsError("Infrastructure profile identity mismatch")
    if set(profile["hosts"]) != SERVICES or set(profile["ports"]) != SERVICES:
        raise SettingsError("Infrastructure endpoint scope mismatch")
    for host in profile["hosts"].values():
        if not isinstance(host, str) or not re.fullmatch(r"[a-z0-9.-]+", host):
            raise SettingsError("Invalid infrastructure host")
    for port in profile["ports"].values():
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise SettingsError("Invalid infrastructure port")
    if (
        profile["secret_contract"] != CONTRACTS[selected]
        or profile["data_class"] != DATA_CLASSES[selected]
    ):
        raise SettingsError("Secret or data-class boundary mismatch")
    if profile["tls_required"] is not (selected == "prod"):
        raise SettingsError("TLS boundary mismatch")
    if selected == "dev" and any(
        ipaddress.ip_address(host) != ipaddress.ip_address("127.0.0.1")
        for host in profile["hosts"].values()
    ):
        raise SettingsError("Development infrastructure must remain loopback-only")
    return profile


def load(selected: str, root: Path = ROOT) -> dict:
    path = root / "deploy/environments" / f"{selected}.yaml"
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise SettingsError("Infrastructure profile escapes project")
    try:
        profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        raise SettingsError("Infrastructure profile cannot be loaded") from None
    return validate(profile, selected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", choices=sorted(ENVIRONMENTS))
    args = parser.parse_args()
    try:
        profile = load(args.environment)
    except SettingsError as exc:
        print(f"infra-settings FAILED: {exc}")
        return 1
    print(
        json.dumps(
            {
                "environment": profile["environment"],
                "services": sorted(SERVICES),
                "tls_required": profile["tls_required"],
                "secret_contract": profile["secret_contract"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
