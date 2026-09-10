"""B-06/B-11 DTOs and pure binding checks; no persistence, authorization or transaction execution."""

from datetime import datetime, timezone
import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .events import OpaqueId, Sequence

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Money(Contract):
    minor_units: Annotated[int, Field(ge=0, le=9007199254740991)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class PageRequest(Contract):
    cursor: OpaqueId | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 20


class PageReferences(Contract):
    items: Annotated[list[OpaqueId], Field(max_length=100)]
    next_cursor: OpaqueId | None
    has_more: bool

    @model_validator(mode="after")
    def cursor_consistency(self):
        if self.has_more != (self.next_cursor is not None):
            raise ValueError("Continuation flag and cursor disagree")
        if len(self.items) != len(set(self.items)):
            raise ValueError("Duplicate page references")
        return self


class ApplicationLine(Contract):
    order_line_id: OpaqueId
    quantity: Annotated[int, Field(ge=1, le=10000)]


class Application(Contract):
    # Applications only: not automatic refunds, payments or order mutations.
    operation: Literal["after_sales.apply"]
    application_type: Literal["RETURN_REFUND", "REFUND_ONLY", "EXCHANGE", "REPAIR", "RESEND"]
    order_id: OpaqueId
    lines: Annotated[list[ApplicationLine], Field(min_length=1, max_length=50)]
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    attachment_refs: Annotated[list[OpaqueId], Field(max_length=20)]

    @model_validator(mode="after")
    def unique_targets(self):
        if len({line.order_line_id for line in self.lines}) != len(self.lines):
            raise ValueError("Duplicate order lines")
        if len(set(self.attachment_refs)) != len(self.attachment_refs):
            raise ValueError("Duplicate attachments")
        if not self.reason.strip():
            raise ValueError("An explicit reason is required")
        return self


def payload_hash(
    application: Application, amount: Money | None, resource_version: str, rule_version: str
) -> str:
    """application-confirmation-v1 canonical hash; not a signature or authorization token.

    Sort only set-like line/attachment lists. Preserve user text, Unicode and integer
    values exactly. No float serialization, NFKC rewriting or LLM-derived amounts.
    """
    body = application.model_dump(mode="json")
    body["lines"] = sorted(body["lines"], key=lambda line: line["order_line_id"])
    body["attachment_refs"] = sorted(body["attachment_refs"])
    canonical = {
        "algorithm": "application-confirmation-v1",
        "application": body,
        "quoted_amount": amount.model_dump() if amount else None,
        "resource_version": resource_version,
        "rule_version": rule_version,
    }
    return hashlib.sha256(
        json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


class PreflightRecord(Contract):
    # SERVER-OWNED record; never accept this whole object as client authority.
    preflight_id: OpaqueId
    tenant_id: OpaqueId
    actor_id: OpaqueId
    application: Application
    quoted_amount: Money | None
    resource_version: OpaqueId
    rule_version: OpaqueId
    payload_hash: Digest
    expires_at: datetime
    state: Literal["PENDING", "USED", "INVALIDATED", "EXPIRED"]
    command_id: OpaqueId | None

    @field_validator("expires_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def consistent_record(self):
        if self.payload_hash != payload_hash(
            self.application, self.quoted_amount, self.resource_version, self.rule_version
        ):
            raise ValueError("Preflight payload hash mismatch")
        if (self.state == "USED") != (self.command_id is not None):
            raise ValueError("Used preflight must bind one command")
        return self


class Submit(Contract):
    preflight_id: OpaqueId
    payload_hash: Digest
    # Transport maps this from Idempotency-Key, not an actor-supplied identity field.
    idempotency_key: OpaqueId


class PageSubmit(Submit):
    channel: Literal["PAGE"]


class ChatSubmit(Submit):
    channel: Literal["CHAT"]
    confirmation_id: OpaqueId
    workflow_id: OpaqueId
    workflow_version: Sequence


def check_binding(
    record: PreflightRecord,
    request: PageSubmit | ChatSubmit,
    *,
    tenant_id: str,
    actor_id: str,
    now: datetime,
) -> str | None:
    """Compare a freshly loaded server record to trusted N2 identity and client references.

    Caller must additionally authorize current resources, verify CHAT confirmation and
    delegation, recheck versions/quantity and atomically bind the command. This function
    neither consumes a preflight nor proves any of these missing checks were performed.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timezone required")
    if (record.tenant_id, record.actor_id) != (tenant_id, actor_id):
        raise ValueError("ACCESS_DENIED")
    # frozen=True does not deeply freeze lists. Recheck the server-owned snapshot
    # so an in-process mutation cannot decouple visible content from its hash.
    record = PreflightRecord.model_validate(record.model_dump())
    if request.preflight_id != record.preflight_id or request.payload_hash != record.payload_hash:
        raise ValueError("IDEMPOTENCY_CONFLICT")
    # Stable reference recovery, not permission to execute again; reauthorize first.
    if record.state == "USED":
        return record.command_id
    if record.state != "PENDING" or now >= record.expires_at:
        raise ValueError("CONFIRMATION_EXPIRED")
    return None


class CommandResult(Contract):
    command_id: OpaqueId
    command_status: (
        Literal["ACCEPTED", "EXECUTING", "SUCCEEDED", "REJECTED", "FAILED", "RECONCILING"] | None
    )
    observation: Literal["KNOWN", "RESULT_UNKNOWN"]
    reason_code: OpaqueId | None
    business_id: OpaqueId | None
    next_action: Literal[
        "QUERY_COMMAND", "REVIEW_RESULT", "REFRESH_AND_RECONFIRM", "CONTACT_SUPPORT"
    ]

    @model_validator(mode="after")
    def truthful_status(self):
        if self.observation == "RESULT_UNKNOWN":
            if (
                self.command_status not in (None, "RECONCILING")
                or self.business_id is not None
                or self.next_action not in ("QUERY_COMMAND", "CONTACT_SUPPORT")
                or self.reason_code is None
            ):
                raise ValueError("Unknown result cannot claim a completed business effect")
        elif self.command_status is None:
            raise ValueError("Known result needs an authoritative status")
        if self.command_status == "RECONCILING" and self.observation != "RESULT_UNKNOWN":
            raise ValueError("Reconciling result remains uncertain")
        return self
