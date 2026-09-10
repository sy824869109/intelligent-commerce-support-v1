"""Use existing locked dependencies, no editable install or external services."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for relative in ("packages/contracts", "packages/persistence", "apps/api-gateway", "scripts"):
    sys.path.insert(0, str(ROOT / relative))
