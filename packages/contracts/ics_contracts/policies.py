"""E-02/E-07 machine-readable design registry; no authorization or retry execution."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ErrorPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    http_statuses: tuple[int, ...]
    retry_policy: Literal[
        "NEVER",
        "BOUNDED_BACKOFF",
        "SAFE_READ_OR_SAME_COMMAND",
        "QUERY_OR_RECONCILE",
        "REPUBLISH_SAME_RESULT",
        "QUARANTINE",
    ]
    client_action: str
    envelope: Literal["error", "data"] = "error"


ERRORS = {
    code: ErrorPolicy(
        http_statuses=statuses, retry_policy=retry, client_action=action, envelope=envelope
    )
    for code, statuses, retry, action, envelope in (
        ("AUTH_REQUIRED", (401,), "NEVER", "REAUTHENTICATE", "error"),
        ("ACCESS_DENIED", (403, 404), "NEVER", "STOP", "error"),
        ("INPUT_INVALID", (422,), "NEVER", "FIX_REQUEST", "error"),
        ("RATE_LIMITED", (429,), "BOUNDED_BACKOFF", "HONOR_RETRY_AFTER", "error"),
        ("IDEMPOTENCY_CONFLICT", (409,), "NEVER", "QUERY_ORIGINAL_REQUEST", "error"),
        ("VERSION_CONFLICT", (409,), "NEVER", "REFRESH_AND_RECONFIRM", "error"),
        ("CONFIRMATION_EXPIRED", (409,), "NEVER", "REFRESH_AND_RECONFIRM", "error"),
        ("RUN_SUPERSEDED", (409,), "NEVER", "READ_SNAPSHOT", "error"),
        (
            "UPSTREAM_UNAVAILABLE",
            (503,),
            "SAFE_READ_OR_SAME_COMMAND",
            "CHECK_OPERATION_SAFETY",
            "error",
        ),
        ("DEADLINE_EXCEEDED", (504,), "QUERY_OR_RECONCILE", "QUERY_COMMAND", "error"),
        ("COMMAND_RESULT_UNKNOWN", (202, 200), "QUERY_OR_RECONCILE", "QUERY_COMMAND", "data"),
        ("PUBLICATION_FAILED", (503,), "REPUBLISH_SAME_RESULT", "READ_SNAPSHOT", "error"),
        ("SCHEMA_UNSUPPORTED", (422,), "QUARANTINE", "QUARANTINE_AND_ALERT", "error"),
    )
}


class OperationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    owner: Literal["N3", "N4_N5", "N5", "N7", "N6", "N3_N4", "N3_N7"]
    effect: Literal["READ", "WRITE", "PRECHECK", "STREAM"]
    authorization: str
    idempotency: Literal["SCOPED_KEY", "NONE", "NO_BUSINESS_EFFECT"]
    timeout_policy: Literal["PROPAGATE_DEADLINE", "REAUTHORIZE_AND_RESUME"]
    implementation: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"


OPERATIONS = {
    name: OperationPolicy(
        owner=owner,
        effect=effect,
        authorization=authorization,
        idempotency="SCOPED_KEY"
        if effect == "WRITE"
        else ("NO_BUSINESS_EFFECT" if effect == "PRECHECK" else "NONE"),
        timeout_policy="REAUTHORIZE_AND_RESUME" if effect == "STREAM" else "PROPAGATE_DEADLINE",
    )
    for name, owner, effect, authorization in (
        ("conversation.create", "N3", "WRITE", "authenticated_actor_in_tenant"),
        ("message.send", "N3", "WRITE", "conversation_and_attachment_access"),
        ("conversation.snapshot", "N3", "READ", "current_conversation_access"),
        ("conversation.events", "N3", "STREAM", "current_conversation_access_each_connection"),
        ("run.cancel", "N3_N4", "WRITE", "run_owner_and_control_epoch"),
        ("workflow.preflight", "N4_N5", "PRECHECK", "delegated_domain_target_access"),
        ("workflow.confirm", "N4_N5", "WRITE", "domain_access_and_current_confirmation"),
        ("commerce.preflight", "N5", "PRECHECK", "domain_operation_and_target_access"),
        ("commerce.submit", "N5", "WRITE", "domain_access_and_confirmation_or_delegation"),
        ("command.get", "N5", "READ", "initiator_or_domain_command_access"),
        ("handoff.request", "N3_N7", "WRITE", "conversation_access"),
        ("ticket.claim", "N7", "WRITE", "agent_assignment_permission_and_version"),
        ("ticket.transfer", "N7", "WRITE", "agent_transfer_permission_and_version"),
        ("ticket.reply", "N7", "WRITE", "active_assignment_and_publication_permission"),
        ("knowledge.upload", "N6", "WRITE", "knowledge_space_upload_permission"),
        ("knowledge.publish", "N6", "WRITE", "approval_permission_and_expected_active_version"),
        ("knowledge.revoke", "N6", "WRITE", "revocation_permission_and_expected_active_version"),
        ("feedback.create", "N3", "WRITE", "conversation_and_formal_message_access"),
    )
}


def registry():
    """Serializable planning metadata; budget numbers remain unfrozen until M17."""
    return {
        "schema_version": 1,
        "status": "DESIGN_CONTRACT_NOT_ROUTES",
        "idempotency_scope": [
            "tenant_id",
            "initiating_actor_id",
            "operation",
            "target_scope",
            "idempotency_key",
        ],
        "retry_rule": "Never change command identity to recover an unknown write result",
        "numeric_deadlines": "UNFROZEN_M17",
        "operations": {key: value.model_dump(mode="json") for key, value in OPERATIONS.items()},
        "errors": {key: value.model_dump(mode="json") for key, value in ERRORS.items()},
    }
