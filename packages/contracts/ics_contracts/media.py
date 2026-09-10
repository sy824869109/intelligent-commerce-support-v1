"""Additive media design contracts; no upload, authorization or download handler."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .api import Empty, Success
from .commerce import Contract, Digest
from .events import OpaqueId
from .handoff import MessageContent, SourcePart, UploadPermitView, UploadRequest


class ChatTarget(Contract):
    kind: Literal["CONVERSATION"]
    conversation_id: OpaqueId


class KnowledgeTarget(Contract):
    kind: Literal["KNOWLEDGE_SPACE"]
    space_id: OpaqueId


class PermitRequest(Contract):
    file: UploadRequest
    target: Annotated[ChatTarget | KnowledgeTarget, Field(discriminator="kind")]

    @model_validator(mode="after")
    def purpose_matches_target(self):
        expected = "CHAT_ATTACHMENT" if isinstance(self.target, ChatTarget) else "KNOWLEDGE_SOURCE"
        if self.file.purpose != expected:
            raise ValueError("Upload purpose and target disagree")
        return self


class UploadObservation(Contract):
    upload_ref: OpaqueId
    state: Literal[
        "PENDING_UPLOAD", "VALIDATING", "READY", "REJECTED", "REVOKED", "DELETING", "DELETED"
    ]
    attachment_ref: OpaqueId | None
    # Knowledge uploads use upload_ref; chat attachment_ref is resolved only after READY.
    purpose: Literal["CHAT_ATTACHMENT", "KNOWLEDGE_SOURCE"]
    verified_sha256: Digest | None

    @model_validator(mode="after")
    def readiness(self):
        if self.state == "READY" and self.verified_sha256 is None:
            raise ValueError("READY needs verified bytes")
        needs_attachment = self.state == "READY" and self.purpose == "CHAT_ATTACHMENT"
        if needs_attachment != (self.attachment_ref is not None):
            raise ValueError("Attachment reference requires a READY chat upload")
        return self


class SourceView(Contract):
    source: SourcePart
    title: Annotated[str, Field(min_length=1, max_length=300)]
    excerpt: Annotated[str, Field(min_length=1, max_length=4000)]
    # Plain text only in rendering; server checks publication and citation ownership.


ERROR_STATUS = {
    "AUTH_REQUIRED": 401,
    "ACCESS_DENIED": 404,
    "INPUT_INVALID": 422,
    "UPLOAD_EXPIRED": 410,
    "UPLOAD_CONFLICT": 409,
    "ASSET_NOT_READY": 409,
    "PAYLOAD_TOO_LARGE": 413,
    "MEDIA_UNSUPPORTED": 415,
    "RATE_LIMITED": 429,
    "UPSTREAM_UNAVAILABLE": 503,
}


class MediaError(Contract):
    code: Literal[
        "AUTH_REQUIRED",
        "ACCESS_DENIED",
        "INPUT_INVALID",
        "UPLOAD_EXPIRED",
        "UPLOAD_CONFLICT",
        "ASSET_NOT_READY",
        "PAYLOAD_TOO_LARGE",
        "MEDIA_UNSUPPORTED",
        "RATE_LIMITED",
        "UPSTREAM_UNAVAILABLE",
    ]
    message: Annotated[str, Field(min_length=1, max_length=500)]


class MediaFailure(Contract):
    request_id: OpaqueId
    trace_id: OpaqueId
    error: MediaError


# Independent extension preserves the previously frozen strict schemas and route inventory.
ROUTES = {
    name: {
        "method": method,
        "path": path,
        "request": request,
        "response": response,
        "status": status,
        "authorization": authorization,
    }
    for name, method, path, request, response, status, authorization in (
        (
            "upload.permit",
            "POST",
            "/api/v1/uploads",
            PermitRequest,
            UploadPermitView,
            201,
            "tenant_actor_target_upload_permission_and_quota",
        ),
        (
            "upload.bytes",
            "PUT",
            "/api/v1/uploads/{upload_ref}/bytes",
            None,
            UploadObservation,
            202,
            "permit_owner_target_purpose_expiry_and_identical_bytes",
        ),
        (
            "upload.get",
            "GET",
            "/api/v1/uploads/{upload_ref}",
            Empty,
            UploadObservation,
            200,
            "permit_owner_and_current_target_access",
        ),
        (
            "message.content",
            "GET",
            "/api/v1/conversations/{conversation_id}/messages/{message_id}/content",
            Empty,
            MessageContent,
            200,
            "current_conversation_access_and_formal_message_membership",
        ),
        (
            "message.source",
            "GET",
            "/api/v1/conversations/{conversation_id}/messages/{message_id}/sources/{source_ref}/versions/{version_ref}/locators/{locator_ref}",
            Empty,
            SourceView,
            200,
            "message_citation_membership_and_current_published_source_access",
        ),
        (
            "message.attachment",
            "GET",
            "/api/v1/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_ref}/bytes",
            Empty,
            None,
            200,
            "message_attachment_membership_and_current_ready_asset_access",
        ),
    )
}


def validate_response(operation: str, status: int, raw: str):
    route = ROUTES[operation]
    if status >= 400:
        result = MediaFailure.model_validate_json(raw)
        if ERROR_STATUS[result.error.code] != status:
            raise ValueError("Media error status mismatch")
        return result
    if status != route["status"] or route["response"] is None:
        raise ValueError("Unexpected media status or binary response")
    result = Success[route["response"]].model_validate_json(raw)
    if operation == "upload.bytes" and result.data.state != "VALIDATING":
        raise ValueError("202 byte receipt only acknowledges validation pending")
    return result


def manifest():
    """Each nested schema is a standalone JSON Schema; this inventory is not OpenAPI."""
    return {
        "status": "DESIGN_ONLY_NOT_IMPLEMENTED",
        "extension_version": 1,
        "authentication": "M03_UNFROZEN_NO_TOKEN_IN_URL",
        "errors": ERROR_STATUS,
        "error_schema": MediaFailure.model_json_schema(),
        "operations": {
            name: {
                "method": route["method"],
                "path": route["path"],
                "authorization": route["authorization"],
                "success_status": route["status"],
                "request_schema": route["request"].model_json_schema()
                if route["request"]
                else None,
                "response_schema": Success[route["response"]].model_json_schema()
                if route["response"]
                else None,
                "request_media_type": "application/octet-stream"
                if route["request"] is None
                else "application/json",
                "response_media_type": "application/json"
                if route["response"]
                else "application/octet-stream",
                "idempotency": "SCOPED_KEY"
                if name == "upload.permit"
                else "SAME_PERMIT_SAME_BYTES"
                if name == "upload.bytes"
                else "READ_ONLY",
                "required_headers": ["Idempotency-Key"]
                if name == "upload.permit"
                else ["Content-Length"]
                if name == "upload.bytes"
                else [],
                "deadline": "PROPAGATE_DEADLINE_NUMERIC_M17",
                "implementation": "NOT_IMPLEMENTED",
            }
            for name, route in ROUTES.items()
        },
    }
