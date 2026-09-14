"""生成/校验 M04.2 商品真实路由合同，不改动 M02/M03 冻结产物。"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
for directory in (
    "apps/api-gateway",
    "apps/commerce-service",
    "packages/persistence",
    "packages/observability",
    "packages/identity",
    "packages/domain",
):
    sys.path.insert(0, str(ROOT / directory))


def export(write=False):
    from ics_gateway.app import create_app
    from ics_gateway.catalog import router
    from ics_gateway.settings import Settings

    app = create_app(Settings(_env_file=None))
    app.include_router(router())
    value = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path = ROOT / "docs/api/m04-catalog.openapi.json"
    if write:
        path.write_text(value, encoding="utf-8", newline="\n")
    elif path.read_text(encoding="utf-8") != value:
        raise ValueError("M04 OpenAPI drift")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    export(parser.parse_args().write)
