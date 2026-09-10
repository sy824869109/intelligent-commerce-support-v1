"""Generate/check deterministic machine contracts and run real offline contract tests."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
for relative in ("packages/contracts", "packages/persistence", "apps/api-gateway"):
    sys.path.insert(0, str(ROOT / relative))


def generated():
    from ics_contracts.events import EVENT_ADAPTER
    from ics_gateway.app import create_app
    from ics_gateway.settings import Settings

    schema = EVENT_ADAPTER.json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Platform browser event v1 (SSE id is envelope cursor)"
    return {
        "packages/contracts/generated/browser-events-v1.schema.json": schema,
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    temp = ROOT / "_local_artifacts/m02-3/tmp"
    temp.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        PYTHONDONTWRITEBYTECODE="1",
        TEMP=str(temp),
        TMP=str(temp),
        RUFF_CACHE_DIR=str(ROOT / "_local_artifacts/caches/ruff"),
    )
    artifacts(write=args.generate)
    if args.generate:
        return 0
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
