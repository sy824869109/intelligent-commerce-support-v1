"""Validated internal event inputs; never a replacement for authenticated tenant context."""

from datetime import datetime, timezone
import hashlib
import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")]


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    event_id: Identifier
    event_type: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.]{0,127}$")]
    schema_version: Annotated[int, Field(gt=0)] = 1
    producer: Identifier
    tenant_id: Identifier
    aggregate_type: Identifier
    aggregate_id: Identifier
    aggregate_version: Annotated[int, Field(gt=0)]
    occurred_at: datetime
    correlation_id: Identifier
    causation_id: Identifier
    trace_id: Identifier
    payload: dict[str, JsonValue]

    @field_validator("occurred_at")
    @classmethod
    def utc_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone-aware occurrence time required")
        return value.astimezone(timezone.utc).replace(microsecond=0)

    @field_validator("payload")
    @classmethod
    def bounded_payload(cls, value):
        # References preferred; never tokens, raw PII or entire documents in an event.
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > 16384:
            raise ValueError("Event payload exceeds 16 KiB")
        return value

    def digest(self):
        raw = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
