"""Planned public DTOs and explicit projections; none registers an HTTP route."""

from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import Field, model_validator

from .commerce import Application, Contract, Digest, Money, PreflightRecord
from .events import Counter, OpaqueId, Sequence
from .policies import ERRORS

Text = Annotated[str, Field(min_length=1, max_length=8192)]
DataT = TypeVar("DataT")


class Success(Contract, Generic[DataT]):
    request_id: OpaqueId
    trace_id: OpaqueId
    data: DataT


class ErrorDetail(Contract):
    code: Literal[
        "AUTH_REQUIRED",
        "ACCESS_DENIED",
        "INPUT_INVALID",
        "RATE_LIMITED",
        "IDEMPOTENCY_CONFLICT",
        "VERSION_CONFLICT",
        "CONFIRMATION_EXPIRED",
        "RUN_SUPERSEDED",
        "UPSTREAM_UNAVAILABLE",
        "DEADLINE_EXCEEDED",
        "PUBLICATION_FAILED",
        "SCHEMA_UNSUPPORTED",
    ]
    message: Annotated[str, Field(min_length=1, max_length=500)]
    retryable: bool
    client_action: str
    command_id: OpaqueId | None

    @model_validator(mode="after")
    def policy_consistency(self):
        policy = ERRORS[self.code]
        if self.client_action != policy.client_action:
            raise ValueError("Error action differs from reviewed policy")
        if self.retryable and policy.retry_policy not in (
            "BOUNDED_BACKOFF",
            "SAFE_READ_OR_SAME_COMMAND",
            "REPUBLISH_SAME_RESULT",
        ):
            raise ValueError("This error cannot authorize an automatic retry")
        return self


class Failure(Contract):
    request_id: OpaqueId
    trace_id: OpaqueId
    error: ErrorDetail


class PreflightView(Contract):
    preflight_id: OpaqueId
    application: Application
    quoted_amount: Money | None
    resource_version: OpaqueId
    rule_version: OpaqueId
    payload_hash: Digest
    expires_at: datetime

    @model_validator(mode="after")
    def aware_expiry(self):
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("Timezone required")
        return self


def public_preflight(record: PreflightRecord) -> PreflightView:
    """Whitelist projection AFTER current actor authorization; never accepts a raw dict.

    Own-order/material references still require access checks. No internal actor,
    tenant, consumption state or command binding is copied into this view.
    """
    checked = PreflightRecord.model_validate(record.model_dump())
    return PreflightView.model_validate(checked.model_dump(include=set(PreflightView.model_fields)))


class ConversationCreate(Contract):
    # Optional business candidate, not proof of ownership or a required synthetic chat.
    business_ref: OpaqueId | None = None


class ConversationView(Contract):
    conversation_id: OpaqueId
    service_mode: Literal["AI", "HANDOFF_PENDING", "HUMAN", "CLOSED"]
    version: Sequence
    control_epoch: Counter
    active_run_id: OpaqueId | None
    active_ticket_id: OpaqueId | None
    assignment_id: OpaqueId | None


class MessageSend(Contract):
    text: Text
    attachment_refs: Annotated[list[OpaqueId], Field(max_length=20)]


class MessageAccepted(Contract):
    message_id: OpaqueId
    run_id: OpaqueId | None
    disposition: Literal["ACCEPTED", "QUEUED", "HUMAN_DELIVERY"]


class MessageView(Contract):
    message_id: OpaqueId
    message_seq: Sequence
    role: Literal["USER", "ASSISTANT", "AGENT"]
    text: Text
    source_refs: Annotated[list[OpaqueId], Field(max_length=50)]


class ConversationSnapshot(Contract):
    conversation: ConversationView
    messages: Annotated[list[MessageView], Field(max_length=100)]
    next_cursor: OpaqueId | None
    has_more: bool
    resume_cursor: OpaqueId | None

    @model_validator(mode="after")
    def page_consistency(self):
        if self.has_more != (self.next_cursor is not None):
            raise ValueError("Pagination cursor mismatch")
        ids = [m.message_id for m in self.messages]
        seq = [m.message_seq for m in self.messages]
        if len(ids) != len(set(ids)) or seq != sorted(set(seq)):
            raise ValueError("Formal history must have unique ascending message sequence")
        return self


class EventsQuery(Contract):
    resume_cursor: OpaqueId | None = None


class RunCancel(Contract):
    control_epoch: Counter


class RunCancelResult(Contract):
    run_id: OpaqueId
    disposition: Literal["CANCEL_REQUESTED", "CANCELLED", "ALREADY_COMPLETED", "SUPERSEDED"]


class WorkflowPreflight(Contract):
    workflow_version: Sequence
    application: Application


class SubmitReferences(Contract):
    preflight_id: OpaqueId
    payload_hash: Digest


class WorkflowConfirm(SubmitReferences):
    workflow_version: Sequence


class Empty(Contract):
    """No request body/query fields; path identifiers are described separately."""


class HandoffRequest(Contract):
    handoff_request_id: OpaqueId
    reason_code: Literal["USER_REQUEST", "COMPLAINT", "SAFETY_ESCALATION", "DEPENDENCY_FAILURE"]


class HandoffResult(Contract):
    handoff_request_id: OpaqueId
    ticket_id: OpaqueId
    disposition: Literal["TICKET_CREATED", "EXISTING_TICKET"]


class TicketClaim(Contract):
    expected_version: Sequence


class TicketTransfer(TicketClaim):
    assignment_id: OpaqueId
    target_agent_id: OpaqueId  # Candidate only, never trusted authority.


class AssignmentResult(Contract):
    ticket_id: OpaqueId
    assignment_id: OpaqueId
    assignment_version: Sequence
    activation_status: Literal["PENDING", "ACTIVE"]


class TicketReply(Contract):
    assignment_id: OpaqueId
    reply_id: OpaqueId
    visibility: Literal["PUBLIC"]
    text: Text


class ReplyResult(Contract):
    reply_id: OpaqueId
    delivery_status: Literal["PENDING", "DELIVERED", "FAILED"]
    formal_message_id: OpaqueId | None

    @model_validator(mode="after")
    def committed_reference(self):
        if (self.delivery_status == "DELIVERED") != (self.formal_message_id is not None):
            raise ValueError("Delivered means formal message saved, not customer read")
        return self


class KnowledgeUpload(Contract):
    # Authorized staging reference, not an arbitrary URL, local path or bucket key.
    upload_ref: OpaqueId
    content_sha256: Digest


class KnowledgeTask(Contract):
    source_id: OpaqueId
    task_id: OpaqueId
    status: Literal["ACCEPTED", "VALIDATING", "REJECTED"]


class KnowledgePublish(Contract):
    target_version: OpaqueId
    expected_active_version: OpaqueId | None
    approval_ref: OpaqueId  # Server verifies current approval and scope.


class KnowledgeRevoke(Contract):
    target_version: OpaqueId
    expected_active_version: OpaqueId
    reason_code: OpaqueId


class KnowledgeVersionResult(Contract):
    version: OpaqueId
    state: Literal["ACTIVE", "REVOKED"]
    audit_id: OpaqueId


class FeedbackCreate(Contract):
    message_id: OpaqueId
    rating: Literal["UP", "DOWN"]
    reason: Annotated[str, Field(max_length=1000)] | None = None


class FeedbackResult(Contract):
    feedback_id: OpaqueId
