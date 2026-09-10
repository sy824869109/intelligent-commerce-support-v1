"""Fixed examples for additive media ports; all execution remains offline."""

import json

import pytest
from pydantic import ValidationError

from ics_contracts.media import ERROR_STATUS, ROUTES, PermitRequest, validate_response

FILE = {
    "purpose": "CHAT_ATTACHMENT",
    "byte_size": 12,
    "content_sha256": "0" * 64,
    "media_type": "image/png",
}
SOURCE = {"kind": "SOURCE", "source_ref": "S1", "version_ref": "V1", "locator_ref": "L1"}
OBSERVATION = {
    "upload_ref": "U1",
    "state": "VALIDATING",
    "purpose": "CHAT_ATTACHMENT",
    "attachment_ref": None,
    "verified_sha256": None,
}
FIXTURES = {
    "upload.permit": {"upload_ref": "U1", "max_bytes": 12, "expires_at": "2026-09-10T02:00:00Z"},
    "upload.bytes": OBSERVATION,
    "upload.get": OBSERVATION,
    "message.content": {"message_id": "M1", "message_seq": 1, "parts": [SOURCE]},
    "message.source": {"source": SOURCE, "title": "退货政策", "excerpt": "以审核后的规则为准。"},
}


def response(data):
    return json.dumps({"request_id": "R1", "trace_id": "T1", "data": data})


@pytest.mark.parametrize("operation", sorted(FIXTURES))
def test_media_response_examples(operation):
    validate_response(operation, ROUTES[operation]["status"], response(FIXTURES[operation]))
    with pytest.raises(ValidationError):
        validate_response(
            operation,
            ROUTES[operation]["status"],
            response(FIXTURES[operation] | {"tenant_id": "T1"}),
        )


def test_all_json_responses_covered_and_binary_not_json():
    assert set(FIXTURES) == {name for name, route in ROUTES.items() if route["response"]}
    with pytest.raises(ValueError, match="binary"):
        validate_response("message.attachment", 200, response({}))


@pytest.mark.parametrize("code,status", ERROR_STATUS.items())
def test_error_statuses(code, status):
    raw = json.dumps(
        {"request_id": "R1", "trace_id": "T1", "error": {"code": code, "message": "请求未完成"}}
    )
    validate_response("upload.bytes", status, raw)
    with pytest.raises(ValueError, match="mismatch"):
        validate_response("upload.bytes", 500, raw)


def test_permit_scope_and_untrusted_authority():
    valid = {"file": FILE, "target": {"kind": "CONVERSATION", "conversation_id": "C1"}}
    PermitRequest.model_validate(valid)
    PermitRequest.model_validate(
        {
            "file": FILE | {"purpose": "KNOWLEDGE_SOURCE"},
            "target": {"kind": "KNOWLEDGE_SPACE", "space_id": "S1"},
        }
    )
    for change in (
        {"actor_id": "A1"},
        {"target": {"kind": "KNOWLEDGE_SPACE", "space_id": "S1"}},
        {"target": {"kind": "CONVERSATION", "conversation_id": "../private"}},
    ):
        with pytest.raises(ValidationError):
            PermitRequest.model_validate(valid | change)


def test_byte_ack_cannot_claim_ready_or_attachment_before_ready():
    ready = OBSERVATION | {"state": "READY", "attachment_ref": "A1", "verified_sha256": "0" * 64}
    validate_response("upload.get", 200, response(ready))
    with pytest.raises(ValueError, match="validation pending"):
        validate_response("upload.bytes", 202, response(ready))
    with pytest.raises(ValidationError):
        validate_response("upload.get", 200, response(OBSERVATION | {"attachment_ref": "A1"}))


def test_extension_baseline_preserves_original(tmp_path, monkeypatch):
    import check_contracts as gate

    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "BASELINE", tmp_path / "baseline.json")
    monkeypatch.setattr(gate, "generated", lambda: {"old.json": {"v": 1}})
    gate.artifacts(write=True)
    gate.compatibility(init=True)
    original = gate.BASELINE.read_bytes()
    monkeypatch.setattr(gate, "generated", lambda: {"old.json": {"v": 1}, "new.json": {"v": 1}})
    gate.artifacts(write=True)
    with pytest.raises(ValueError, match="Frozen"):
        gate.compatibility()
    gate.compatibility(extend=True)
    gate.compatibility()
    assert gate.BASELINE.read_bytes() == original
    with pytest.raises(FileExistsError):
        gate.compatibility(extend=True)
    monkeypatch.setattr(gate, "generated", lambda: {"old.json": {"v": 2}, "new.json": {"v": 1}})
    gate.artifacts(write=True)
    with pytest.raises(ValueError, match="Frozen"):
        gate.compatibility(extend=True)
    with pytest.raises(ValueError, match="Frozen"):
        gate.compatibility()
