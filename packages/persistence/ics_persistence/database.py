"""Bounded synchronous MySQL access; each operation owns one short transaction."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class DatabaseConfig:
    username: str
    password: str = field(repr=False)
    database: str
    host: str = "127.0.0.1"
    port: int = 23306

    def url(self) -> URL:
        # M02 is synthetic-data, local-only. Do not silently enable remote/plaintext DB access.
        if self.host != "127.0.0.1" or not 1024 <= self.port <= 65535:
            raise ValueError("Database target must be an unprivileged loopback endpoint")
        if not self.username or not self.password or not self.database:
            raise ValueError("Database credentials and schema are required")
        return URL.create(
            "mysql+pymysql",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
            query={"charset": "utf8mb4"},
        )


class Database:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._health_lock = Lock()
        # No shared Session, implicit auto-begin or reusable closed sessions.
        self.sessions = sessionmaker(
            engine,
            expire_on_commit=False,
            autoflush=False,
            autobegin=False,
            close_resets_only=False,
        )

    @classmethod
    def connect(cls, config: DatabaseConfig):
        return cls(
            create_engine(
                config.url(),
                pool_size=5,
                max_overflow=0,
                pool_timeout=2,
                pool_recycle=1800,
                pool_pre_ping=True,
                hide_parameters=True,
                isolation_level="READ COMMITTED",
                echo=False,
                connect_args={
                    "connect_timeout": 2,
                    "read_timeout": 2,
                    "write_timeout": 2,
                    "init_command": "SET time_zone = '+00:00', innodb_lock_wait_timeout = 2",
                },
            )
        )

    @contextmanager
    def transaction(self):
        """Commit once on success; rollback on all exceptions. No network/model work inside."""
        with self.sessions.begin() as session:
            yield session

    def ready(self) -> bool:
        from .version import HEAD

        # A cancelled HTTP waiter cannot cancel a DBAPI call; cap outstanding probes at one.
        if not self._health_lock.acquire(blocking=False):
            return False
        try:
            with self.engine.connect() as connection:
                return connection.execute(
                    text("SELECT version_num FROM platform_alembic_version")
                ).scalars().all() == [HEAD]
        except Exception:
            # Never expose driver exceptions/connection arguments to HTTP or logs.
            return False
        finally:
            self._health_lock.release()

    def close(self) -> None:
        self.engine.dispose()


def require_transaction(session: Session) -> None:
    if not session.in_transaction():
        raise RuntimeError("An explicit owner transaction is required")
