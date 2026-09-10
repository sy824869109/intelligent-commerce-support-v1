"""App-specific settings; never implicitly load the legacy root .env or M01 secrets."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ICS_GATEWAY_", extra="forbid", frozen=True)

    environment: Literal["dev", "test"] = "dev"
    # Production/LAN deployment is deliberately not enabled before M03 authentication.
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=28000, ge=1024, le=65535)
    docs_enabled: bool = True
    allowed_origins: tuple[str, ...] = ("http://127.0.0.1:28000",)
    readiness_timeout_seconds: float = Field(default=1.0, gt=0, le=5)

    @model_validator(mode="after")
    def reserved_ports(self):
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (
                not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.scheme not in {"http", "https"}
                or "*" in origin
                or (parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost"})
            ):
                raise ValueError("Origins must be explicit HTTPS origins or loopback HTTP origins")
        if self.port in {23306, 26379, 28333, 29530}:
            raise ValueError("Gateway port conflicts with M01 infrastructure")
        return self
