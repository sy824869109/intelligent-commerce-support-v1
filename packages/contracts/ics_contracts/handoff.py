"""Message/source and cursor/upload boundary contracts, not storage or access services."""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, field_validator, model_validator

from .commerce import Contract, Digest
from .events import OpaqueId, Sequence


class TextPart(Contract):
    kind: Literal["TEXT"]
    text: Annotated[str, Field(min_length=1, max_length=8192)]


class SourcePart(Contract):
    kind: Literal["SOURCE"]
    source_ref: OpaqueId
    version_ref: OpaqueId
    locator_ref: OpaqueId


class AttachmentPart(Contract):
    kind: Literal["ATTACHMENT"]
    attachment_ref: OpaqueId


MessagePart = Annotated[TextPart | SourcePart | AttachmentPart, Field(discriminator="kind")]
PART_ADAPTER = TypeAdapter(MessagePart)


class MessageContent(Contract):
    # Separate content contract, not an additive field silently injected into strict HTTP v1.
    message_id: OpaqueId
    message_seq: Sequence
    parts: Annotated[list[MessagePart], Field(min_length=1, max_length=50)]


class Expiring(Contract):
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone required")
        return value.astimezone(timezone.utc)


class CursorBinding(Expiring):
    # Server-side lookup record. Public clients see only an opaque random token.
    cursor: OpaqueId
    tenant_id: OpaqueId
    actor_id: OpaqueId
    resource_id: OpaqueId
    purpose: Literal["HISTORY_PAGE", "EVENT_RESUME"]
    query_hash: Digest


def check_cursor(
    record: CursorBinding,
    *,
    cursor: str,
    tenant_id: str,
    actor_id: str,
    resource_id: str,
    purpose: str,
    query_hash: str,
    now: datetime,
):
    """Bind an already loaded server record; caller still reauthorizes every connection/read.

    Token generation and storage are N3 responsibilities. No raw client JSON record,
    unsigned self-contained payload or timestamp is treated as authorization evidence.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timezone required")
    expected = (
        record.cursor,
        record.tenant_id,
        record.actor_id,
        record.resource_id,
        record.purpose,
        record.query_hash,
    )
    if expected != (cursor, tenant_id, actor_id, resource_id, purpose, query_hash):
        raise ValueError("CURSOR_SCOPE_MISMATCH")
    if now >= record.expires_at:
        raise ValueError("CURSOR_EXPIRED")


class UploadRequest(Contract):
    purpose: Literal["CHAT_ATTACHMENT", "KNOWLEDGE_SOURCE"]
    byte_size: Annotated[int, Field(ge=1, le=33554432)]
    content_sha256: Digest
    media_type: Literal["text/plain", "application/pdf", "image/png", "image/jpeg"]


class UploadPermit(Expiring):
    upload_ref: OpaqueId
    tenant_id: OpaqueId
    actor_id: OpaqueId
    request: UploadRequest


class UploadPermitView(Expiring):
    upload_ref: OpaqueId
    max_bytes: Annotated[int, Field(ge=1, le=33554432)]


class AssetValidation(Contract):
    # Server-owned observation: validity of these fields is not proof scanners ran.
    upload_ref: OpaqueId
    state: Literal[
        "PENDING_UPLOAD", "VALIDATING", "READY", "REJECTED", "REVOKED", "DELETING", "DELETED"
    ]
    malware_check: Literal["NOT_RUN", "PASSED", "FAILED"]
    format_check: Literal["NOT_RUN", "PASSED", "FAILED"]
    verified_sha256: Digest | None

    @model_validator(mode="after")
    def ready_requires_checks(self):
        if self.state == "READY" and (
            self.malware_check != "PASSED"
            or self.format_check != "PASSED"
            or self.verified_sha256 is None
        ):
            raise ValueError("Unchecked upload cannot be READY")
        return self
