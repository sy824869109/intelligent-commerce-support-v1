"""Synthetic scope/expiry/content tests; no cursor issuer, upload or scanner is running."""

from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
import pytest

from ics_contracts.handoff import (
    AssetValidation,
    CursorBinding,
    MessageContent,
    UploadRequest,
    check_cursor,
)

NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


def test_message_content_accepts_only_typed_references_not_external_paths():
    MessageContent(
        message_id="M1",
        message_seq=1,
        parts=[
            {"kind": "TEXT", "text": "政策说明"},
            {"kind": "SOURCE", "source_ref": "S1", "version_ref": "V1", "locator_ref": "LOC1"},
            {"kind": "ATTACHMENT", "attachment_ref": "A1"},
        ],
    )
    for part in (
        {
            "kind": "SOURCE",
            "source_ref": "https://example.org/file",
            "version_ref": "V1",
            "locator_ref": "L1",
        },
        {"kind": "SOURCE", "source_ref": "S1", "locator_ref": "L1"},
        {"kind": "HTML", "text": "untrusted"},
        {"kind": "ATTACHMENT", "attachment_ref": "../../private"},
    ):
        with pytest.raises(ValidationError):
            MessageContent(message_id="M1", message_seq=1, parts=[part])


def test_cursor_is_bound_to_identity_resource_query_purpose_and_time():
    args = {
        "cursor": "CUR1",
        "tenant_id": "T1",
        "actor_id": "U1",
        "resource_id": "C1",
        "purpose": "HISTORY_PAGE",
        "query_hash": "0" * 64,
    }
    record = CursorBinding(**args, expires_at=NOW + timedelta(minutes=5))
    check_cursor(record, **args, now=NOW)
    for field in args:
        with pytest.raises(ValueError, match="CURSOR_SCOPE_MISMATCH"):
            check_cursor(record, **(args | {field: "different"}), now=NOW)
    with pytest.raises(ValueError, match="CURSOR_EXPIRED"):
        check_cursor(record, **args, now=record.expires_at)
    with pytest.raises(ValueError, match="Timezone required"):
        check_cursor(record, **args, now=NOW.replace(tzinfo=None))


@pytest.mark.parametrize(
    "change",
    [
        {"byte_size": 0},
        {"byte_size": 33554433},
        {"byte_size": True},
        {"media_type": "application/x-executable"},
        {"purpose": "ARBITRARY"},
        {"local_path": "private"},
    ],
)
def test_upload_permit_request_is_bounded(change):
    with pytest.raises(ValidationError):
        UploadRequest.model_validate(
            {
                "purpose": "KNOWLEDGE_SOURCE",
                "byte_size": 10,
                "content_sha256": "0" * 64,
                "media_type": "application/pdf",
            }
            | change
        )


def test_ready_cannot_be_claimed_without_both_checks_and_digest():
    valid = {
        "upload_ref": "UP1",
        "state": "READY",
        "malware_check": "PASSED",
        "format_check": "PASSED",
        "verified_sha256": "0" * 64,
    }
    AssetValidation.model_validate(valid)
    for change in (
        {"malware_check": "NOT_RUN"},
        {"format_check": "FAILED"},
        {"verified_sha256": None},
    ):
        with pytest.raises(ValidationError):
            AssetValidation.model_validate(valid | change)
