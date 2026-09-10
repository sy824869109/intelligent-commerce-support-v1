"""Generate/check deterministic machine contracts and run real offline contract tests."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "packages/contracts/compatibility/v1-artifacts.sha256.json"
for relative in (
    "packages/contracts",
    "packages/persistence",
    "packages/observability",
    "apps/api-gateway",
):
    sys.path.insert(0, str(ROOT / relative))


def generated():
    from ics_contracts.media import manifest as media_manifest
    from ics_contracts.events import EVENT_ADAPTER
    from ics_contracts.domain import PublicReply
    from ics_contracts.policies import registry
    from ics_contracts.routes import manifest
    from ics_contracts.handoff import (
        AssetValidation,
        CursorBinding,
        MessageContent,
        UploadPermit,
        UploadPermitView,
        UploadRequest,
    )
    from ics_contracts.commerce import (
        Application,
        ChatSubmit,
        CommandResult,
        Money,
        PageReferences,
        PageRequest,
        PageSubmit,
        PreflightRecord,
    )
    from ics_persistence.events import Event
    from ics_gateway.app import create_app
    from ics_gateway.settings import Settings

    schema = EVENT_ADAPTER.json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Platform browser event v1 (SSE id is envelope cursor)"
    return {
        "packages/contracts/generated/media-routes-v1.design.json": media_manifest(),
        "packages/contracts/generated/business-routes-v1.design.json": manifest(),
        **{
            "packages/contracts/generated/" + name + "-v1.schema.json": model.model_json_schema()
            for name, model in {
                "application": Application,
                "chat-submit": ChatSubmit,
                "page-submit": PageSubmit,
                "command-result": CommandResult,
                "money": Money,
                "page-request": PageRequest,
                "page-references": PageReferences,
                "preflight-record": PreflightRecord,
                "message-content": MessageContent,
                "cursor-binding": CursorBinding,
                "upload-request": UploadRequest,
                "upload-permit": UploadPermit,
                "upload-permit-view": UploadPermitView,
                "asset-validation": AssetValidation,
            }.items()
        },
        "packages/contracts/generated/browser-events-v1.schema.json": schema,
        "packages/contracts/generated/domain-envelope.schema.json": Event.model_json_schema(),
        "packages/contracts/generated/public-reply-v1.schema.json": PublicReply.model_json_schema(),
        "packages/contracts/generated/operation-policies-v1.json": registry(),
        "packages/contracts/generated/gateway.openapi.json": create_app(
            Settings(_env_file=None)
        ).openapi(),
    }


def artifacts(write=False):
    for relative, value in generated().items():
        path = ROOT / relative
        expected = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8", newline="\n")
        elif not path.is_file() or path.read_text(encoding="utf-8") != expected:
            raise ValueError("Generated contract drift: " + relative)


def compatibility(init=False, extend=False):
    """An immutable first-release snapshot, independent of ordinary schema regeneration.

    Exact matching is intentionally conservative. A deliberate evolution needs an
    explicit version/migration review; --generate cannot bless a breaking change.
    """
    actual = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(generated())
    }
    if init:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation; never overwrite a reviewed baseline on a repeat run.
        with BASELINE.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(actual, indent=2, sort_keys=True) + "\n")
        return
    frozen = json.loads(BASELINE.read_text(encoding="utf-8"))
    extension = BASELINE.with_name("v1-media-extension.sha256.json")
    if extend:
        if any(actual.get(name) != digest for name, digest in frozen.items()):
            raise ValueError("Frozen v1 contract changed; extension cannot replace old contracts")
        additions = {name: digest for name, digest in actual.items() if name not in frozen}
        if not additions:
            raise ValueError("No new artifacts to review")
        with extension.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(additions, indent=2, sort_keys=True) + "\n")
        return
    if extension.is_file():
        additions = json.loads(extension.read_text(encoding="utf-8"))
        if frozen.keys() & additions.keys():
            raise ValueError("Extension cannot shadow frozen contracts")
        frozen.update(additions)
    if frozen != actual:
        raise ValueError(
            "Frozen v1 contract changed; explicit compatibility/version review required"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--init-baseline", action="store_true")
    parser.add_argument("--init-media-extension", action="store_true")
    args = parser.parse_args()
    if args.init_baseline and args.init_media_extension:
        parser.error("Choose only one baseline initialization")
    temp = ROOT / "_local_artifacts/m02-3/tmp"
    temp.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        PYTHONDONTWRITEBYTECODE="1",
        TEMP=str(temp),
        TMP=str(temp),
        RUFF_CACHE_DIR=str(ROOT / "_local_artifacts/caches/ruff"),
    )
    artifacts(write=args.generate)
    if args.init_baseline:
        compatibility(init=True)
        return 0
    if args.init_media_extension:
        compatibility(extend=True)
        return 0
    if args.generate:
        return 0
    compatibility()
    for command in (
        [
            "-m",
            "ruff",
            "check",
            "--config",
            "ci/ruff.toml",
            "packages/contracts",
            "tests/contracts",
        ],
        [
            "-m",
            "ruff",
            "format",
            "--check",
            "--config",
            "ci/ruff.toml",
            "packages/contracts",
            "tests/contracts",
        ],
        ["-m", "bandit", "-q", "-r", "packages/contracts"],
        [
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/contracts",
            "--basetemp",
            str(temp / "pytest"),
        ],
    ):
        subprocess.run([sys.executable, *command], cwd=ROOT, check=True)
    print("M02.3 contract foundation PASS; no business endpoint or SSE transport is live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
