"""Run only the new loopback gateway; existing Docker services are untouched."""

import logging
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "apps/api-gateway"))
sys.path.insert(0, str(ROOT / "packages/persistence"))
sys.path.insert(0, str(ROOT / "packages/observability"))


def main() -> int:
    from pydantic import ValidationError
    import uvicorn
    from ics_gateway.settings import Settings
    from ics_gateway.app import create_app

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-database", action="store_true", help="Verify and use only M01 local MySQL"
    )
    args = parser.parse_args()

    try:
        settings = Settings()
    except ValidationError:
        print("Gateway configuration invalid; check ICS_GATEWAY_* settings (values withheld).")
        return 1
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    database = None
    if args.with_database:
        from database_local import load_database

        try:
            database = load_database()
        except Exception:
            print("Local database configuration/ownership invalid; values withheld.")
            return 1
    uvicorn.run(
        create_app(settings, database=database),
        host=settings.host,
        port=settings.port,
        access_log=False,
        proxy_headers=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
