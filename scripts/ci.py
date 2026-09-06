"""Run the same M00.4 checks in Conda/PyCharm and on GitHub-hosted runners.

Fail on the first broken gate. Never start application services, read reference
archives, publish images or claim that business acceptance cases have run.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(arguments: list[str]) -> None:
    """Use argv (no shell interpolation) and propagate any nonzero exit status."""
    print("CI > " + " ".join(arguments), flush=True)
    subprocess.run(arguments, cwd=ROOT, check=True)


def main() -> int:
    """Only foundation checks are enabled until runtime modules exist."""
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    python = sys.executable
    expected = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    actual = ".".join(str(part) for part in sys.version_info[:3])
    if actual != expected:
        print(f"Foundation CI FAILED: Python {actual}, expected {expected}")
        return 1
    try:
        for script in (
            "verify_structure.py",
            "verify_governance.py",
            "verify_implementation_standards.py",
            "verify_ci.py",
        ):
            run([python, "scripts/" + script])
        run([python, "-m", "ruff", "check", "--config", "ci/ruff.toml", "scripts", "tests/unit"])
        run(
            [
                python,
                "-m",
                "ruff",
                "format",
                "--check",
                "--config",
                "ci/ruff.toml",
                "scripts",
                "tests/unit",
            ]
        )
        # Parse tracked Python, including diagram generators, without import side effects.
        paths = subprocess.check_output(["git", "ls-files", "-z", "--", "*.py"], cwd=ROOT)
        for item in paths.split(b"\0"):
            if item:
                relative = item.decode("utf-8")
                ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
        run([python, "scripts/run_unit_tests.py"])
        # Merge-commit first-parent diff checks PR changes; push checks latest atomic step.
        parent = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^"], cwd=ROOT, capture_output=True
        )
        if parent.returncode == 0:
            run(["git", "diff", "--check", "HEAD^", "HEAD"])
        run(["git", "diff", "--check"])
    except (subprocess.CalledProcessError, OSError, SyntaxError, UnicodeError) as exc:
        print(f"Foundation CI FAILED: {type(exc).__name__}")
        return 1
    message = (
        "Foundation checks PASS. Backend/frontend/runtime contracts/SAST/dependency "
        "audit/image build are NOT_IMPLEMENTED; 93 business cases remain NOT_RUN.\n"
    )
    print(message)
    # GitHub-provided summary destination only; no arbitrary user file argument.
    if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write("## M00.4 scope\n\n" + message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
