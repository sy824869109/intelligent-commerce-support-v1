"""Public projections and all planned request shapes; tests do not call business APIs."""

from datetime import datetime, timedelta, timezone
import json

from pydantic import ValidationError
import pytest

from ics_contracts import api
from ics_contracts.commerce import Application, PreflightRecord, payload_hash
from ics_contracts.policies import ERRORS, OPERATIONS
from ics_contracts.routes import ROUTES, SUCCESS_STATUSES, manifest, validate_response

APP = {
    "operation": "after_sales.apply",
    "application_type": "RETURN_REFUND",
    "order_id": "O1",
    "lines": [{"order_line_id": "L1", "quantity": 1}],
    "reason": "尺码不合适",
    "attachment_refs": [],
}
REF = {"preflight_id": "P1", "payload_hash": "0" * 64}
REQUESTS = {
    "conversation.create": {},
    "message.send": {"text": "你好", "attachment_refs": []},
    "conversation.snapshot": {"limit": 20},
    "conversation.events": {},
    "run.cancel": {"control_epoch": 1},
    "workflow.preflight": {"workflow_version": 1, "application": APP},
    "workflow.confirm": REF | {"workflow_version": 1},
    "commerce.preflight": APP,
    "commerce.submit": REF,
    "command.get": {},
    "handoff.request": {"handoff_request_id": "H1", "reason_code": "USER_REQUEST"},
    "ticket.claim": {"expected_version": 1},
    "ticket.transfer": {"expected_version": 1, "assignment_id": "A1", "target_agent_id": "U2"},
    "ticket.reply": {
        "assignment_id": "A1",
        "reply_id": "R1",
        "visibility": "PUBLIC",
        "text": "回复",
    },
    "knowledge.upload": {"upload_ref": "UP1", "content_sha256": "0" * 64},
    "knowledge.publish": {
        "target_version": "V2",
        "expected_active_version": "V1",
        "approval_ref": "AP1",
    },
    "knowledge.revoke": {
        "target_version": "V2",
        "expected_active_version": "V2",
        "reason_code": "INCORRECT",
    },
    "feedback.create": {"message_id": "M1", "rating": "UP"},
}


@pytest.mark.parametrize("operation", sorted(REQUESTS))
def test_every_planned_request_has_positive_example_and_rejects_actor_spoof(operation):
    model = ROUTES[operation]["request"]
    model.model_validate(REQUESTS[operation])
    for forbidden in ("actor_id", "tenant_id", "roles", "confirmed", "idempotency_key"):
        with pytest.raises(ValidationError):
            model.model_validate(REQUESTS[operation] | {forbidden: "synthetic"})


def test_inventory_exact_coverage_unique_routes_and_auth_boundaries():
    design = manifest()
    assert set(REQUESTS) == set(ROUTES) == set(OPERATIONS) == set(SUCCESS_STATUSES)
    assert len({(r["method"], r["path"]) for r in ROUTES.values()}) == 18
    assert design["status"] == "DESIGN_ONLY_NOT_LIVE_OPENAPI"
    for name, route in design["operations"].items():
        assert route["implementation"] == "NOT_IMPLEMENTED"
        assert route["request_schema"] in design["schemas"]
        assert route["response_schema"] in design["schemas"]
        assert ("Idempotency-Key" in route["required_headers"]) == (
            OPERATIONS[name].effect == "WRITE"
        )
        assert "token" not in route["path"]
    assert ROUTES["workflow.preflight"]["audience"] == "VERIFIED_SERVICE"


def test_preflight_projection_excludes_private_fields_and_preserves_bound_payload():
    app = Application.model_validate(APP)
    record = PreflightRecord(
        preflight_id="P1",
        tenant_id="T1",
        actor_id="U1",
        application=app,
        quoted_amount=None,
        resource_version="V1",
        rule_version="RULE1",
        payload_hash=payload_hash(app, None, "V1", "RULE1"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        state="PENDING",
        command_id=None,
    )
    view = api.public_preflight(record)
    assert not {"actor_id", "tenant_id", "state", "command_id"} & view.model_dump().keys()
    assert view.payload_hash == record.payload_hash
    assert view.application == record.application
    with pytest.raises(ValidationError):
        api.PreflightView.model_validate(record.model_dump())


def error(code):
    return {
        "request_id": "REQ1",
        "trace_id": "TRACE1",
        "error": {
            "code": code,
            "message": "请求无法处理",
            "retryable": False,
            "client_action": ERRORS[code].client_action,
            "command_id": None,
        },
    }


@pytest.mark.parametrize("code", sorted(set(ERRORS) - {"COMMAND_RESULT_UNKNOWN"}))
def test_error_envelopes_and_http_mapping(code):
    for status in ERRORS[code].http_statuses:
        validate_response("commerce.submit", status, json.dumps(error(code)))
    with pytest.raises(ValueError):
        validate_response("commerce.submit", 599, json.dumps(error(code)))


def test_unknown_result_is_data_and_cannot_mix_success_and_error():
    body = {
        "request_id": "R1",
        "trace_id": "T1",
        "data": {
            "command_id": "C1",
            "command_status": None,
            "observation": "RESULT_UNKNOWN",
            "reason_code": "COMMAND_RESULT_UNKNOWN",
            "business_id": None,
            "next_action": "QUERY_COMMAND",
        },
    }
    validate_response("commerce.submit", 202, json.dumps(body))
    with pytest.raises(ValidationError):
        validate_response(
            "commerce.submit", 202, json.dumps(body | {"error": error("INPUT_INVALID")["error"]})
        )
    with pytest.raises(ValidationError):
        api.Failure.model_validate(error("COMMAND_RESULT_UNKNOWN"))


def test_error_cannot_enable_blind_retry_or_invent_action():
    body = error("DEADLINE_EXCEEDED")
    body["error"]["retryable"] = True
    with pytest.raises(ValidationError):
        api.Failure.model_validate(body)
    body = error("AUTH_REQUIRED")
    body["error"]["client_action"] = "RETRY_PAYMENT"
    with pytest.raises(ValidationError):
        api.Failure.model_validate(body)


def test_claims_of_delivery_require_formal_message_and_notes_are_not_public_reply():
    with pytest.raises(ValidationError):
        api.ReplyResult(reply_id="R1", delivery_status="DELIVERED", formal_message_id=None)
    with pytest.raises(ValidationError):
        api.TicketReply.model_validate(REQUESTS["ticket.reply"] | {"visibility": "INTERNAL"})


def test_server_paths_and_external_urls_are_not_upload_references():
    for candidate in ("https://example.org/file", "C:/secret", "../../secret"):
        with pytest.raises(ValidationError):
            api.KnowledgeUpload(upload_ref=candidate, content_sha256="0" * 64)


def test_terminal_command_is_not_202_accepted():
    body = {
        "request_id": "R1",
        "trace_id": "T1",
        "data": {
            "command_id": "C1",
            "command_status": "SUCCEEDED",
            "observation": "KNOWN",
            "reason_code": None,
            "business_id": "B1",
            "next_action": "REVIEW_RESULT",
        },
    }
    validate_response("commerce.submit", 200, json.dumps(body))
    with pytest.raises(ValueError):
        validate_response("commerce.submit", 202, json.dumps(body))
