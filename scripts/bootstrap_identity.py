"""Interactive one-time local tenant administrator bootstrap; no default credentials."""

import argparse
from getpass import getpass
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
for directory in ("packages/persistence", "packages/observability", "packages/identity"):
    sys.path.insert(0, str(ROOT / directory))


def main():
    from sqlalchemy import select
    from database_local import load_database
    from ics_persistence.identity_schema import tenants
    from ics_identity.passwords import hash_password
    from ics_identity.service import provision_tenant, username

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    username(args.username)
    if not sys.stdin.isatty():
        raise RuntimeError("Interactive password entry is required")
    password = getpass("Administrator password (15..128 characters): ")
    if password != getpass("Repeat password: "):
        raise ValueError("Passwords do not match")
    encoded = hash_password(password)
    del password
    database = load_database()
    try:
        if not database.ready():
            raise RuntimeError("Upgrade the reviewed database first")
        with database.transaction() as session:
            # Operator-only initial installation; never overwrite an existing identity setup.
            if session.scalar(select(tenants.c.id).limit(1)):
                raise RuntimeError("Identity already initialized; use authenticated administration")
            tenant_id = uuid4().hex
            provision_tenant(
                session,
                organization_id=uuid4().hex,
                tenant_id=tenant_id,
                user_id=uuid4().hex,
                login=args.username,
                password_hash=encoded,
            )
        print("Administrator created. Tenant ID: " + tenant_id)
        print("No password or token was written to a file.")
    finally:
        database.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Bootstrap failed; database/credential details withheld. Check policy and initialization state."
        )
        raise SystemExit(1) from None
