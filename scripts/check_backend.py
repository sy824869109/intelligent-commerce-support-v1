"""Real M02.1 gates, separate from the dependency-free foundation checks."""

from pathlib import Path
import argparse
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(*arguments: str) -> None:
    subprocess.run([sys.executable, *arguments], cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=["tests", "security"])
    args = parser.parse_args()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    # Local dependencies and every tool cache stay under the project, including on Windows.
    cache_root = ROOT / "_local_artifacts/caches"
    temp = ROOT / "_local_artifacts/m02-1/tmp"
    temp.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = os.environ["TMP"] = os.environ["TMPDIR"] = str(temp)
    os.environ["RUFF_CACHE_DIR"] = str(cache_root / "ruff")
    os.environ["PIP_CACHE_DIR"] = str(cache_root / "pip")
    try:
        if args.gate == "tests":
            run("-m", "pip", "check")
            run("-m", "ruff", "check", "--config", "ci/ruff.toml", "apps", "tests/backend")
            run(
                "-m",
                "ruff",
                "format",
                "--check",
                "--config",
                "ci/ruff.toml",
                "apps",
                "tests/backend",
            )
            # pytest exits 5 when no tests are collected; subprocess preserves that failure.
            run("-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/backend")
        else:
            run("-m", "bandit", "-r", "apps", "scripts/run_gateway.py", "-q")
            # Both app and test/tool dependency sets are pinned; no ignore-vuln exemptions.
            for lock in ("apps/api-gateway/requirements.lock", "ci/backend-requirements.lock"):
                run(
                    "-m",
                    "pip_audit",
                    "--no-deps",
                    "--disable-pip",
                    "--cache-dir",
                    str(cache_root / "pip-audit"),
                    "-r",
                    lock,
                )
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
