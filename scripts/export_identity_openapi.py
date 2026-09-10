"""Generate/check M03 identity OpenAPI without changing the frozen M02 artifact."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
for directory in (
    "apps/api-gateway",
    "packages/persistence",
    "packages/observability",
    "packages/identity",
):
    sys.path.insert(0, str(ROOT / directory))


def export(write=False):
    from ics_gateway.app import create_app
    from ics_gateway.identity import router
    from ics_gateway.settings import Settings

    app = create_app(Settings(_env_file=None))
    app.include_router(router())
    value = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path = ROOT / "docs/api/m03-identity.openapi.json"
    if write:
        path.write_text(value, encoding="utf-8", newline="\n")
    elif path.read_text(encoding="utf-8") != value:
        raise ValueError("M03 OpenAPI drift")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    export(parser.parse_args().write)
