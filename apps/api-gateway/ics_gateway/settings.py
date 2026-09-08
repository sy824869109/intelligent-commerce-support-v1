"""App-specific settings; never implicitly load the legacy root .env or M01 secrets."""

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ICS_GATEWAY_", extra="forbid", frozen=True)

    environment: Literal["dev", "test"] = "dev"
    # Production/LAN deployment is deliberately not enabled before M03 authentication.
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=28000, ge=1024, le=65535)
    docs_enabled: bool = True
    readiness_timeout_seconds: float = Field(default=1.0, gt=0, le=5)

    @model_validator(mode="after")
    def reserved_ports(self):
        if self.port in {23306, 26379, 28333, 29530}:
            raise ValueError("Gateway port conflicts with M01 infrastructure")
        return self
