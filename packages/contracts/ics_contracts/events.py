"""E-03 browser wire contracts, not KF events or proof of authorization/publication."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, field_validator

OpaqueId = Annotated[
    str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
]
Counter = Annotated[int, Field(ge=0, le=9007199254740991)]
Sequence = Annotated[int, Field(ge=1, le=9007199254740991)]


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1]
    conversation_id: OpaqueId
    control_epoch: Counter

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        # Python equates True/1/1.0; the JSON contract requires an actual integer version.
        if type(value) is not int:
            raise ValueError("Schema version must be an integer")
        return value


class RunEvent(Event):
    run_id: OpaqueId


class Started(RunEvent):
    event_type: Literal["run.started"]
    cursor: OpaqueId


class Progress(RunEvent):
    event_type: Literal["run.progress"]
    # Whitelisted machine progress; never arbitrary exception/prompt text.
    stage: Literal["QUEUED", "RETRIEVING", "GENERATING", "PUBLISHING"]


class Delta(RunEvent):
    event_type: Literal["answer.delta"]
    token_seq: Sequence
    text: Annotated[str, Field(min_length=1, max_length=8192)]


class Committed(Event):
    event_type: Literal["message.committed"]
    cursor: OpaqueId
    run_id: OpaqueId | None  # Human messages have no AI Run; explicit null is required.
    message_id: OpaqueId
    message_seq: Sequence


class Completed(RunEvent):
    event_type: Literal["run.completed"]
    cursor: OpaqueId
    final_message_id: OpaqueId


class Failed(RunEvent):
    event_type: Literal["run.failed"]
    cursor: OpaqueId
    reason_code: Literal[
        "DEADLINE_EXCEEDED", "UPSTREAM_UNAVAILABLE", "PUBLICATION_FAILED", "RUN_SUPERSEDED"
    ]
    next_action: Literal["READ_SNAPSHOT", "QUERY_COMMAND", "CONTACT_SUPPORT"]
    command_id: OpaqueId | None


class Control(Event):
    event_type: Literal["control.changed"]
    cursor: OpaqueId
    service_mode: Literal["AI", "HANDOFF_PENDING", "HUMAN", "CLOSED"]
    active_run_id: OpaqueId | None
    assignment_id: OpaqueId | None


class Resync(Event):
    event_type: Literal["resync_required"]
    reason: Literal["CURSOR_EXPIRED", "DELTA_MISSING", "BUFFER_EXCEEDED"]
    next_action: Literal["READ_SNAPSHOT"]


BrowserEvent = Annotated[
    Started | Progress | Delta | Committed | Completed | Failed | Control | Resync,
    Field(discriminator="event_type"),
]
EVENT_ADAPTER = TypeAdapter(BrowserEvent)
MAX_FRAME_BYTES = 65536


def encode_sse(value: dict) -> bytes:
    """Validate before encoding; ephemeral deltas/progress never advance recovery cursors.

    Callers still must authorize, check epoch/output policy and persist final results.
    A valid DTO alone does not grant publication or establish any database fact.
    """
    event = EVENT_ADAPTER.validate_python(value)
    data = event.model_dump()
    cursor = data.pop("cursor", None)
    lines = (["id: " + cursor] if cursor else []) + [
        "event: " + event.event_type,
        "data: " + json.dumps(data, ensure_ascii=False, separators=(",", ":")),
    ]
    frame = ("\n".join(lines) + "\n\n").encode("utf-8")
    if len(frame) > MAX_FRAME_BYTES:
        raise ValueError("SSE frame exceeds the fixed wire budget")
    return frame
