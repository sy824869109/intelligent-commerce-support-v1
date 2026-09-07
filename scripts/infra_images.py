"""Build or verify the five reviewed M01 images; never publish or remove images."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORDER = ("mysql", "redis", "etcd", "seaweedfs", "milvus")


def lock() -> dict[str, str]:
    data = json.loads((ROOT / "deploy/compose/images.lock.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 2 or set(data.get("images", {})) != set(ORDER):
        raise ValueError("M01 image lock scope changed")
    return data["images"]


def run(arguments: list[str], *, timeout: int = 7200) -> str:
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("reviewed image operation failed; detailed build output withheld")
    return result.stdout.strip()


def verify(images: dict[str, str]) -> None:
    for name in ORDER:
        reference = images[name]
        expected = reference.rsplit("@", 1)[1]
        actual = run(["docker", "image", "inspect", reference, "--format", "{{.Id}}"])
        if actual != expected:
            raise RuntimeError(f"{name} local image does not match the reviewed digest")
    print("M01 image lock PASS: five local images match reviewed digests")


def build(images: dict[str, str]) -> None:
    for name in ORDER:
        reference = images[name]
        tag = reference.split("@", 1)[0]
        context = ROOT / "deploy/images" / name
        run(
            [
                "docker",
                "build",
                "--pull",
                "--provenance=false",
                "--sbom=false",
                "--progress=plain",
                "--platform=linux/amd64",
                "--file",
                str(context / "Dockerfile"),
                "--tag",
                tag,
                str(context),
            ]
        )
    verify(images)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    try:
        images = lock()
        build(images) if args.action == "build" else verify(images)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"infra-images FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
