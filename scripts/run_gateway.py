"""Run only the new loopback gateway; existing Docker services are untouched."""

import logging
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "apps/api-gateway"))


def main() -> int:
    from pydantic import ValidationError
    import uvicorn
    from ics_gateway.settings import Settings

    try:
        settings = Settings()
    except ValidationError:
        print("Gateway configuration invalid; check ICS_GATEWAY_* settings (values withheld).")
        return 1
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    uvicorn.run(
        "ics_gateway.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        access_log=False,
        proxy_headers=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
