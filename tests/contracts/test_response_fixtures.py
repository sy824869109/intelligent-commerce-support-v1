"""Reviewed v1 response fixtures, deliberately not regenerated from current models."""

import json

from pydantic import ValidationError
import pytest

from ics_contracts.routes import ROUTES, validate_response
from ics_contracts.commerce import Application, payload_hash

APP = {
    "operation": "after_sales.apply",
    "application_type": "RETURN_REFUND",
    "order_id": "O1",
    "lines": [{"order_line_id": "L1", "quantity": 1}],
    "reason": "尺码不合适",
    "attachment_refs": [],
}
VIEW = {
    "conversation_id": "C1",
    "service_mode": "AI",
    "version": 1,
    "control_epoch": 0,
    "active_run_id": None,
    "active_ticket_id": None,
    "assignment_id": None,
}
PREFLIGHT = {
    "preflight_id": "P1",
    "application": APP,
    "quoted_amount": None,
    "resource_version": "V1",
    "rule_version": "RULE1",
    "payload_hash": "08d44f3d1e9560e212bfb84d6ffef6ea1b45efd908d1e778960f7124e8c62598",
    "expires_at": "2026-09-10T01:00:00Z",
}
COMMAND = {
    "command_id": "CMD1",
    "command_status": None,
    "observation": "RESULT_UNKNOWN",
    "reason_code": "COMMAND_RESULT_UNKNOWN",
    "business_id": None,
    "next_action": "QUERY_COMMAND",
}
ASSIGNMENT = {
    "ticket_id": "T1",
    "assignment_id": "A1",
    "assignment_version": 1,
    "activation_status": "PENDING",
}
RESPONSES = {
    "conversation.create": VIEW,
    "message.send": {"message_id": "M1", "run_id": "R1", "disposition": "ACCEPTED"},
    "conversation.snapshot": {
        "conversation": VIEW,
        "messages": [],
        "next_cursor": None,
        "has_more": False,
        "resume_cursor": None,
    },
    "run.cancel": {"run_id": "R1", "disposition": "CANCEL_REQUESTED"},
    "workflow.preflight": PREFLIGHT,
    "workflow.confirm": COMMAND,
    "commerce.preflight": PREFLIGHT,
    "commerce.submit": COMMAND,
    "command.get": COMMAND,
    "handoff.request": {
        "handoff_request_id": "H1",
        "ticket_id": "T1",
        "disposition": "TICKET_CREATED",
    },
    "ticket.claim": ASSIGNMENT,
    "ticket.transfer": ASSIGNMENT,
    "ticket.reply": {"reply_id": "R1", "delivery_status": "PENDING", "formal_message_id": None},
    "knowledge.upload": {"source_id": "S1", "task_id": "TASK1", "status": "ACCEPTED"},
    "knowledge.publish": {"version": "V1", "state": "ACTIVE", "audit_id": "AUDIT1"},
    "knowledge.revoke": {"version": "V1", "state": "REVOKED", "audit_id": "AUDIT1"},
    "feedback.create": {"feedback_id": "F1"},
}


@pytest.mark.parametrize("operation", sorted(RESPONSES))
def test_frozen_public_response_examples_and_no_extra_authority(operation):
    body = {"request_id": "REQ1", "trace_id": "TRACE1", "data": RESPONSES[operation]}
    validate_response(operation, 200, json.dumps(body))
    with pytest.raises(ValidationError):
        validate_response(
            operation, 200, json.dumps(body | {"data": body["data"] | {"actor_id": "U1"}})
        )


def test_all_json_operations_have_reviewed_fixture():
    assert set(RESPONSES) == {
        name for name, route in ROUTES.items() if route["response"] is not None
    }


def test_confirmation_hash_golden_vector():
    # Filled once at baseline creation and reviewed in git, not derived on each test run.
    assert (
        payload_hash(Application.model_validate(APP), None, "V1", "RULE1")
        == "08d44f3d1e9560e212bfb84d6ffef6ea1b45efd908d1e778960f7124e8c62598"
    )
