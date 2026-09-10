"""Contract-reader compatibility with M02.2 storage, not consumer/ACK integration."""

import json

from pydantic import ValidationError
import pytest

from ics_contracts.domain import read_public_reply, UnsupportedEvent
from ics_contracts.policies import ERRORS, OPERATIONS, registry
from ics_persistence.events import Event


def fixture():
    return {
        "event_id": "EV001",
        "event_type": "ticket.public_reply.created",
        "schema_version": 1,
        "producer": "ticket-service",
        "tenant_id": "TENANT_A",
        "aggregate_type": "ticket",
        "aggregate_id": "T001",
        "aggregate_version": 8,
        "occurred_at": "2026-09-06T04:00:00Z",
        "correlation_id": "C001",
        "causation_id": "CMD_REPLY001",
        "trace_id": "TR001",
        "payload": {
            "reply_id": "REPLY001",
            "conversation_id": "C001",
            "assignment_id": "ASSIGN001",
            "visibility": "PUBLIC",
            "content_ref": "REPLY001",
        },
    }


def test_existing_event_round_trip_and_digest_unchanged():
    raw = json.dumps(fixture())
    stored = Event.model_validate_json(raw)
    decoded = read_public_reply(raw)
    assert decoded.model_dump() == stored.model_dump()
    assert decoded.digest() == stored.digest()
    assert read_public_reply(decoded.model_dump_json()).event_id == stored.event_id


@pytest.mark.parametrize("field,value", [("event_type", "future.event"), ("schema_version", 2)])
def test_unsupported_event_must_not_be_guessed(field, value):
    with pytest.raises(UnsupportedEvent, match="SCHEMA_UNSUPPORTED"):
        read_public_reply(json.dumps(fixture() | {field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("producer", "untrusted"),
        ("aggregate_type", "order"),
        ("schema_version", True),
        ("aggregate_version", 0),
        ("occurred_at", "2026-09-06T04:00:00"),
        ("tenant_id", ""),
        ("event_id", "E\nV"),
    ],
)
def test_invalid_envelope_rejected(field, value):
    with pytest.raises(ValueError):
        read_public_reply(json.dumps(fixture() | {field: value}))


@pytest.mark.parametrize(
    "field,value", [("visibility", "INTERNAL"), ("assignment_id", ""), ("raw_text", "private")]
)
def test_payload_private_or_invalid_fields_rejected(field, value):
    event = fixture()
    event["payload"][field] = value
    with pytest.raises(ValidationError):
        read_public_reply(json.dumps(event))


def test_missing_original_reference_rejected():
    event = fixture()
    del event["payload"]["content_ref"]
    with pytest.raises(ValidationError):
        read_public_reply(json.dumps(event))


def test_large_wire_input_rejected():
    with pytest.raises(ValueError, match="wire budget"):
        read_public_reply(" " * 32769)


def test_unknown_command_result_is_data_not_error_or_blind_retry():
    policy = ERRORS["COMMAND_RESULT_UNKNOWN"]
    assert policy.envelope == "data"
    assert policy.http_statuses == (202, 200)
    assert policy.retry_policy == "QUERY_OR_RECONCILE"
    assert ERRORS["DEADLINE_EXCEEDED"].retry_policy == "QUERY_OR_RECONCILE"
    assert ERRORS["PUBLICATION_FAILED"].retry_policy == "REPUBLISH_SAME_RESULT"


def test_every_write_has_scoped_idempotency_and_authorization():
    assert len(OPERATIONS) == 18
    assert len(ERRORS) == 13
    for operation in OPERATIONS.values():
        assert operation.authorization
        assert operation.implementation == "NOT_IMPLEMENTED"
        if operation.effect == "WRITE":
            assert operation.idempotency == "SCOPED_KEY"
    assert registry()["numeric_deadlines"] == "UNFROZEN_M17"


def test_page_and_chat_use_same_domain_confirmation_policy():
    assert OPERATIONS["workflow.confirm"].idempotency == OPERATIONS["commerce.submit"].idempotency
    assert OPERATIONS["commerce.preflight"].effect == "PRECHECK"
    assert OPERATIONS["conversation.events"].timeout_policy == "REAUTHORIZE_AND_RESUME"
