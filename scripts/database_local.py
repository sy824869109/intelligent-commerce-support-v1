"""M02.2: explicitly verify the new M01 MySQL, then inspect/upgrade its foundation schema."""

import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "packages/persistence"))


def load_database():
    """No root credential or legacy file access. Do not print config, URL or DBAPI exceptions."""
    from ics_persistence.database import Database, DatabaseConfig
    import local_infra as infra

    folder = ROOT / "deploy/compose"
    env_file = folder / ".env"
    secret_file = folder / "secrets/mysql_password"
    for path in (env_file, secret_file):
        infra.ensure_local_path(path, folder)
    config = infra.parse_env(env_file.read_text(encoding="utf-8"))
    password = secret_file.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[a-f0-9]{64}", password):
        raise ValueError("Invalid local secret")
    environment = infra.compose_environment(dict(os.environ))
    docker = infra.docker_prefix(environment)
    ids = infra.invoke(
        docker
        + [
            "ps",
            "-q",
            "--filter",
            "label=com.docker.compose.project=ics-v1-dev",
            "--filter",
            "label=com.docker.compose.service=mysql",
        ],
        environment,
    ).stdout.split()
    if len(ids) != 1:
        raise ValueError("Exactly one running new-platform MySQL is required")
    record = json.loads(infra.invoke(docker + ["inspect", ids[0]], environment).stdout)[0]
    labels = record["Config"]["Labels"]
    expected_image = json.loads((folder / "images.lock.json").read_text(encoding="utf-8"))[
        "images"
    ]["mysql"].split("@")[-1]
    if (
        labels.get("org.ics.instance") != config["INFRA_INSTANCE_ID"]
        or Path(labels.get("com.docker.compose.project.working_dir", "")).resolve()
        != folder.resolve()
        or record["Image"] != expected_image
        or record["NetworkSettings"]["Ports"].get("3306/tcp")
        != [{"HostIp": "127.0.0.1", "HostPort": config["MYSQL_PORT"]}]
        or record["State"].get("Health", {}).get("Status") != "healthy"
    ):
        raise ValueError("MySQL ownership/image/endpoint/health does not match M01")
    runtime_env = dict(item.split("=", 1) for item in record["Config"]["Env"] if "=" in item)
    if any(runtime_env.get(key) != config[key] for key in ("MYSQL_DATABASE", "MYSQL_USER")):
        raise ValueError("MySQL schema/user mismatch")
    return Database.connect(
        DatabaseConfig(
            username=config["MYSQL_USER"],
            password=password,
            database=config["MYSQL_DATABASE"],
            port=int(config["MYSQL_PORT"]),
        )
    )


def main():
    from ics_persistence.migration import migrate

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "upgrade"])
    args = parser.parse_args()
    database = None
    try:
        database = load_database()
        if args.action == "upgrade":
            migrate(database.engine)
        ready = database.ready()
        print("M02 database/migration: " + ("READY" if ready else "NOT_READY"))
        return 0 if ready else 1
    except Exception:
        print("M02 local database operation failed; configuration and SQL details withheld.")
        return 1
    finally:
        if database is not None:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
