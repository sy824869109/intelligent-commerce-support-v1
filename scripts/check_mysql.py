"""Real MySQL integration in one owned ephemeral container; no existing volumes touched."""

import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "packages/persistence"))


def main():
    from ics_persistence.database import Database, DatabaseConfig
    import local_infra as infra

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci", action="store_true", help="Use this CI job's reviewed built image")
    args = parser.parse_args()
    environment = infra.compose_environment(dict(os.environ))
    docker = infra.docker_prefix(environment)
    locked = json.loads((ROOT / "deploy/compose/images.lock.json").read_text(encoding="utf-8"))[
        "images"
    ]["mysql"]
    image = "ics-mysql:ci" if args.ci else locked
    # --ci is not an arbitrary-image escape hatch on a user's computer.
    if args.ci and os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("CI image mode requires the GitHub runner")
    infra.invoke(docker + ["image", "inspect", image], environment)
    marker = uuid.uuid4().hex
    name = "ics-m02-test-" + marker
    environment.update(
        MYSQL_ROOT_PASSWORD=secrets.token_hex(32), MYSQL_PASSWORD=secrets.token_hex(32)
    )
    temp = ROOT / "_local_artifacts/m02-2/tmp"
    temp.mkdir(parents=True, exist_ok=True)
    environment.update(
        TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1"
    )
    database = None
    try:
        infra.invoke(
            docker
            + [
                "run",
                "-d",
                "--pull=never",
                "--name",
                name,
                "--label",
                "org.ics.m02-test=" + marker,
                "--memory",
                "2g",
                "--cpus",
                "2",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/var/lib/mysql:rw,nosuid,size=1g",
                "-p",
                "127.0.0.1::3306",
                "-e",
                "MYSQL_ROOT_PASSWORD",
                "-e",
                "MYSQL_PASSWORD",
                "-e",
                "MYSQL_DATABASE=ics_m02_test",
                "-e",
                "MYSQL_USER=ics_m02_test",
                image,
                "--innodb-buffer-pool-size=128M",
                "--max-connections=30",
            ],
            environment,
        )
        record = json.loads(infra.invoke(docker + ["inspect", name], environment).stdout)[0]
        bindings = record["NetworkSettings"]["Ports"]["3306/tcp"]
        if len(bindings) != 1 or bindings[0]["HostIp"] != "127.0.0.1":
            raise RuntimeError("Unexpected ephemeral endpoint")
        port = int(bindings[0]["HostPort"])
        database = Database.connect(
            DatabaseConfig(
                username="ics_m02_test",
                password=environment["MYSQL_PASSWORD"],
                database="ics_m02_test",
                port=port,
            )
        )
        from sqlalchemy import text

        deadline = time.monotonic() + 120
        while True:
            try:
                with database.engine.connect() as connection:
                    if not connection.scalar(text("SELECT VERSION()")).startswith("8.4.11"):
                        raise RuntimeError("Unexpected MySQL version")
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Ephemeral MySQL did not become ready") from None
                time.sleep(2)
        environment["ICS_TEST_MYSQL_PASSWORD"] = environment.pop("MYSQL_PASSWORD")
        environment.pop("MYSQL_ROOT_PASSWORD")
        environment["ICS_TEST_MYSQL_PORT"] = str(port)
        completed = infra.invoke(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                "tests/integration/test_m02_mysql.py",
                "--basetemp",
                str(temp / ("pytest-" + marker)),
            ],
            environment,
            timeout=300,
            required=False,
        )
        print(completed.stdout)
        if completed.stderr:
            print(completed.stderr)
        return completed.returncode
    finally:
        if database is not None:
            database.close()
        result = infra.invoke(docker + ["inspect", name], environment, required=False)
        if result.returncode == 0:
            record = json.loads(result.stdout)[0]
            if (
                record["Config"].get("Labels", {}).get("org.ics.m02-test") != marker
                or record["Name"] != "/" + name
            ):
                raise RuntimeError("Refusing cleanup: ephemeral container ownership changed")
            # Exact owned temporary container only. No volume delete, prune or Compose down.
            infra.invoke(docker + ["rm", "-f", record["Id"]], environment)
            print("Removed only this run's temporary MySQL container and synthetic tmpfs data.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("MySQL integration runner failed; credentials/driver details withheld.")
        raise SystemExit(1) from None
