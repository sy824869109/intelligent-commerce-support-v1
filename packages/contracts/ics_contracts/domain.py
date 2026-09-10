"""E-06 supported domain-event reader, reusing M02.2's persisted envelope unchanged."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from ics_persistence.events import Event, Identifier


class UnsupportedEvent(ValueError):
    """Caller must quarantine durably before ACK; this module performs no ACK or I/O."""


class PublicReply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    reply_id: Identifier
    conversation_id: Identifier
    assignment_id: Identifier
    visibility: Literal["PUBLIC"]
    content_ref: Identifier


def read_public_reply(raw: str) -> Event:
    """Validate the wire envelope and the only currently registered domain payload.

    Producer/tenant claims are NOT authenticated by parsing. N8/N3 must verify the
    real service identity, assignment, original reply and recipient authorization.
    Unknown type/version fails closed; never mutate or fabricate replay event IDs.
    """
    if len(raw.encode("utf-8")) > 32768:
        raise ValueError("Domain event exceeds wire budget")
    event = Event.model_validate_json(raw)
    if (event.event_type, event.schema_version) != ("ticket.public_reply.created", 1):
        raise UnsupportedEvent("SCHEMA_UNSUPPORTED")
    if event.producer != "ticket-service" or event.aggregate_type != "ticket":
        raise ValueError("Unexpected event producer or aggregate type")
    PublicReply.model_validate(event.payload)
    return event
