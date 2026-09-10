"""Design-only route manifest. Deliberately separate from the live Gateway OpenAPI."""

import re

from . import api
from .commerce import Application, CommandResult, PageRequest
from .events import EVENT_ADAPTER, OpaqueId
from .policies import ERRORS, OPERATIONS


# Body excludes trusted actor/tenant/roles and Idempotency-Key, which is a header.
# N4 invokes the same N5 domain port under a verified delegation, not browser identity fields.
ROUTES = {
    operation: {
        "method": method,
        "path": path,
        "request": request,
        "response": response,
        "request_location": location,
        "audience": audience,
    }
    for operation, method, path, request, response, location, audience in (
        (
            "conversation.create",
            "POST",
            "/api/v1/conversations",
            api.ConversationCreate,
            api.ConversationView,
            "body",
            "N2_PUBLIC",
        ),
        (
            "message.send",
            "POST",
            "/api/v1/conversations/{conversation_id}/messages",
            api.MessageSend,
            api.MessageAccepted,
            "body",
            "N2_PUBLIC",
        ),
        (
            "conversation.snapshot",
            "GET",
            "/api/v1/conversations/{conversation_id}/snapshot",
            PageRequest,
            api.ConversationSnapshot,
            "query",
            "N2_PUBLIC",
        ),
        (
            "conversation.events",
            "GET",
            "/api/v1/conversations/{conversation_id}/events",
            api.EventsQuery,
            None,
            "query",
            "N2_PUBLIC",
        ),
        (
            "run.cancel",
            "POST",
            "/api/v1/conversations/{conversation_id}/runs/{run_id}/cancel",
            api.RunCancel,
            api.RunCancelResult,
            "body",
            "N2_PUBLIC",
        ),
        (
            "workflow.preflight",
            "POST",
            "/internal/v1/workflows/{workflow_id}/preflight",
            api.WorkflowPreflight,
            api.PreflightView,
            "body",
            "VERIFIED_SERVICE",
        ),
        (
            "workflow.confirm",
            "POST",
            "/api/v1/workflows/{workflow_id}/confirmations/{confirmation_id}/submit",
            api.WorkflowConfirm,
            CommandResult,
            "body",
            "N2_PUBLIC",
        ),
        (
            "commerce.preflight",
            "POST",
            "/api/v1/commerce/preflights",
            Application,
            api.PreflightView,
            "body",
            "N2_PUBLIC",
        ),
        (
            "commerce.submit",
            "POST",
            "/api/v1/commerce/commands",
            api.SubmitReferences,
            CommandResult,
            "body",
            "N2_PUBLIC",
        ),
        (
            "command.get",
            "GET",
            "/api/v1/commerce/commands/{command_id}",
            api.Empty,
            CommandResult,
            "query",
            "N2_PUBLIC",
        ),
        (
            "handoff.request",
            "POST",
            "/api/v1/conversations/{conversation_id}/handoffs",
            api.HandoffRequest,
            api.HandoffResult,
            "body",
            "N2_PUBLIC",
        ),
        (
            "ticket.claim",
            "POST",
            "/api/v1/tickets/{ticket_id}/claim",
            api.TicketClaim,
            api.AssignmentResult,
            "body",
            "N2_PUBLIC",
        ),
        (
            "ticket.transfer",
            "POST",
            "/api/v1/tickets/{ticket_id}/transfer",
            api.TicketTransfer,
            api.AssignmentResult,
            "body",
            "N2_PUBLIC",
        ),
        (
            "ticket.reply",
            "POST",
            "/api/v1/tickets/{ticket_id}/replies",
            api.TicketReply,
            api.ReplyResult,
            "body",
            "N2_PUBLIC",
        ),
        (
            "knowledge.upload",
            "POST",
            "/api/v1/knowledge/spaces/{space_id}/sources",
            api.KnowledgeUpload,
            api.KnowledgeTask,
            "body",
            "N2_PUBLIC",
        ),
        (
            "knowledge.publish",
            "POST",
            "/api/v1/knowledge/spaces/{space_id}/publications",
            api.KnowledgePublish,
            api.KnowledgeVersionResult,
            "body",
            "N2_PUBLIC",
        ),
        (
            "knowledge.revoke",
            "POST",
            "/api/v1/knowledge/spaces/{space_id}/revocations",
            api.KnowledgeRevoke,
            api.KnowledgeVersionResult,
            "body",
            "N2_PUBLIC",
        ),
        (
            "feedback.create",
            "POST",
            "/api/v1/conversations/{conversation_id}/feedback",
            api.FeedbackCreate,
            api.FeedbackResult,
            "body",
            "N2_PUBLIC",
        ),
    )
}

SUCCESS_STATUSES = {
    "conversation.create": [200, 201],
    "message.send": [200, 201, 202],
    "conversation.snapshot": [200],
    "conversation.events": [200],
    "run.cancel": [200, 202],
    "workflow.preflight": [200, 201],
    "workflow.confirm": [200, 202],
    "commerce.preflight": [200, 201],
    "commerce.submit": [200, 202],
    "command.get": [200],
    "handoff.request": [200, 201],
    "ticket.claim": [200, 202],
    "ticket.transfer": [200, 202],
    "ticket.reply": [200, 201, 202],
    "knowledge.upload": [200, 201, 202],
    "knowledge.publish": [200],
    "knowledge.revoke": [200],
    "feedback.create": [200, 201],
}


def validate_response(operation: str, status: int, raw: str):
    """Offline JSON response validation; never used as evidence that an API exists."""
    route = ROUTES[operation]
    if status >= 400:
        result = api.Failure.model_validate_json(raw)
        if status not in ERRORS[result.error.code].http_statuses:
            raise ValueError("Error code and HTTP status disagree")
        return result
    if status not in SUCCESS_STATUSES[operation] or route["response"] is None:
        raise ValueError("Unexpected success status or non-JSON stream")
    result = api.Success[route["response"]].model_validate_json(raw)
    if status == 202 and isinstance(result.data, CommandResult):
        if result.data.command_status in ("SUCCEEDED", "REJECTED", "FAILED"):
            raise ValueError("202 cannot describe a definitive terminal result")
    return result


def manifest():
    """Schema-linked inventory, not an OpenAPI listing of callable operations."""
    from pydantic import TypeAdapter

    operations = {}
    schemas = {"Failure": api.Failure.model_json_schema()}
    for name, route in ROUTES.items():
        policy = OPERATIONS[name]
        request, response = route["request"], route["response"]
        schemas[request.__name__] = request.model_json_schema()
        if response is not None:
            # The actual response model is an envelope, not a naked business DTO.
            key = "Success_" + response.__name__
            schemas[key] = api.Success[response].model_json_schema()
        else:
            key = "BrowserEvent"
            schemas[key] = EVENT_ADAPTER.json_schema()
        operations[name] = {
            "method": route["method"],
            "path": route["path"],
            "audience": route["audience"],
            "implementation": "NOT_IMPLEMENTED",
            "request_location": route["request_location"],
            "request_schema": request.__name__,
            "response_schema": key,
            "response_media_type": "application/json" if response else "text/event-stream",
            "error_schema": "Failure",
            "stream_errors": "run.failed or resync_required after stream starts"
            if response is None
            else None,
            "path_parameters": {
                key: TypeAdapter(OpaqueId).json_schema()
                for key in re.findall(r"\{([^}]+)\}", route["path"])
            },
            "required_headers": ["Idempotency-Key"] if policy.effect == "WRITE" else [],
            "authorization_rule": policy.authorization,
            "deadline_policy": policy.timeout_policy,
            "success_http_statuses": SUCCESS_STATUSES[name],
        }
    return {
        "schema_version": 1,
        "status": "DESIGN_ONLY_NOT_LIVE_OPENAPI",
        "authentication": "M03_UNFROZEN_NO_TOKEN_IN_URL",
        "operations": operations,
        "schemas": schemas,
    }
