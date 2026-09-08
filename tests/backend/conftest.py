"""Backend tests import the app without installing a mutable editable package."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/api-gateway"))
