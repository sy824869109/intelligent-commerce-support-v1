"""Synthetic wire and live in-process HTTP contracts, not business acceptance."""

import json

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from ics_contracts.events import EVENT_ADAPTER, encode_sse
from ics_gateway.app import create_app
from ics_gateway.settings import Settings
from check_contracts import artifacts

BASE = {"schema_version": 1, "conversation_id": "C001", "control_epoch": 4}
EXAMPLES = [
    {"event_type": "run.started", "run_id": "R001", "cursor": "cursor-1"},
    {"event_type": "run.progress", "run_id": "R001", "stage": "RETRIEVING"},
    {"event_type": "answer.delta", "run_id": "R001", "token_seq": 1, "text": "您好"},
    {
        "event_type": "message.committed",
        "run_id": "R001",
        "cursor": "cursor-2",
        "message_id": "M002",
        "message_seq": 2,
    },
    {
        "event_type": "run.completed",
        "run_id": "R001",
        "cursor": "cursor-3",
        "final_message_id": "M002",
    },
    {
        "event_type": "run.failed",
        "run_id": "R001",
        "cursor": "cursor-4",
        "reason_code": "PUBLICATION_FAILED",
        "next_action": "READ_SNAPSHOT",
        "command_id": None,
    },
    {
        "event_type": "control.changed",
        "cursor": "cursor-5",
        "service_mode": "HUMAN",
        "active_run_id": None,
        "assignment_id": "A001",
    },
    {"event_type": "resync_required", "reason": "DELTA_MISSING", "next_action": "READ_SNAPSHOT"},
]


@pytest.mark.parametrize("example", EXAMPLES)
def test_all_eight_event_variants_round_trip(example):
    value = BASE | example
    assert EVENT_ADAPTER.validate_json(json.dumps(value)).model_dump() == value
    frame = encode_sse(value).decode()
    assert frame.endswith("\n\n")
    assert ("id: " in frame) == ("cursor" in example)
    assert "event: " + example["event_type"] + "\n" in frame
    body = json.loads(next(line[6:] for line in frame.splitlines() if line.startswith("data: ")))
    assert body == {k: v for k, v in value.items() if k != "cursor"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("schema_version", 1.0),
        ("control_epoch", -1),
        ("control_epoch", True),
        ("control_epoch", "4"),
        ("conversation_id", "x\nid: injected"),
        ("run_id", ""),
        ("token_seq", 0),
        ("token_seq", 9007199254740992),
        ("text", ""),
        ("text", "x" * 8193),
        ("cursor", "illegal"),
        ("access_token", "synthetic"),
        ("event_type", "token"),
    ],
)
def test_malformed_delta_is_rejected(field, value):
    with pytest.raises(ValidationError):
        encode_sse(BASE | EXAMPLES[2] | {field: value})


def test_newlines_in_text_cannot_inject_sse_fields():
    frame = encode_sse(BASE | EXAMPLES[2] | {"text": "你好\nevent: run.completed\n\nid: evil"})
    assert len(frame.decode().splitlines()) == 3
    assert not frame.startswith(b"id:")


def test_completed_requires_formal_message_reference():
    value = BASE | EXAMPLES[4]
    del value["final_message_id"]
    with pytest.raises(ValidationError):
        encode_sse(value)


def test_failed_cannot_claim_success():
    with pytest.raises(ValidationError):
        encode_sse(BASE | EXAMPLES[5] | {"success": True})


def test_untrusted_progress_diagnostic_is_rejected():
    with pytest.raises(ValidationError):
        encode_sse(BASE | EXAMPLES[1] | {"stage": "private prompt"})


def test_human_committed_message_has_no_run():
    assert EVENT_ADAPTER.validate_python(BASE | EXAMPLES[3] | {"run_id": None}).run_id is None


def test_generated_files_match_current_sources():
    artifacts()


def test_openapi_contains_only_real_health_routes_and_http_shapes():
    app = create_app(Settings(_env_file=None))
    schema = app.openapi()
    assert set(schema["paths"]) == {"/health/live", "/health/ready"}
    with TestClient(app) as client:
        for path in schema["paths"]:
            response = client.get(path)
            assert response.status_code == 200
            assert set(response.json()) == {"request_id", "trace_id", "data"}
        assert client.post("/api/chat").status_code == 404


def test_unready_is_error_not_success():
    async def unavailable():
        return False

    with TestClient(
        create_app(Settings(_env_file=None), checks={"synthetic": unavailable})
    ) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert set(response.json()) == {"request_id", "trace_id", "error"}
