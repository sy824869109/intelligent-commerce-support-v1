"""Synthetic confirmation DTO checks; no order access, authorization or writes."""

from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
import pytest

from ics_contracts.commerce import (
    Application,
    ChatSubmit,
    CommandResult,
    Money,
    PageReferences,
    PageRequest,
    PageSubmit,
    PreflightRecord,
    check_binding,
    payload_hash,
)

NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


def application():
    return Application(
        operation="after_sales.apply",
        application_type="RETURN_REFUND",
        order_id="O001",
        lines=[{"order_line_id": "L001", "quantity": 1}],
        reason="尺码不合适",
        attachment_refs=[],
    )


def record():
    app = application()
    amount = Money(minor_units=19900, currency="CNY")
    return PreflightRecord(
        preflight_id="P001",
        tenant_id="T001",
        actor_id="U001",
        application=app,
        quoted_amount=amount,
        resource_version="v8",
        rule_version="v2",
        payload_hash=payload_hash(app, amount, "v8", "v2"),
        expires_at=NOW + timedelta(minutes=5),
        state="PENDING",
        command_id=None,
    )


def submit(rec, channel="PAGE"):
    args = {
        "preflight_id": rec.preflight_id,
        "payload_hash": rec.payload_hash,
        "idempotency_key": "K001",
        "channel": channel,
    }
    return (
        PageSubmit(**args)
        if channel == "PAGE"
        else ChatSubmit(**args, confirmation_id="CF001", workflow_id="W001", workflow_version=1)
    )


@pytest.mark.parametrize("channel", ["PAGE", "CHAT"])
def test_both_channels_same_preflight_checks(channel):
    rec = record()
    assert (
        check_binding(rec, submit(rec, channel), tenant_id="T001", actor_id="U001", now=NOW) is None
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("minor_units", 1.5),
        ("minor_units", True),
        ("minor_units", -1),
        ("currency", "cny"),
        ("currency", ""),
    ],
)
def test_money_rejects_float_boolean_negative_or_missing_currency(field, value):
    with pytest.raises(ValidationError):
        Money.model_validate({"minor_units": 10, "currency": "CNY"} | {field: value})


@pytest.mark.parametrize(
    "change",
    [
        {"lines": []},
        {"lines": [{"order_line_id": "L001", "quantity": 0}]},
        {"lines": [{"order_line_id": "L001", "quantity": 1}] * 2},
        {"reason": "   "},
        {"operation": "refund.execute"},
        {"confirmed": True},
        {"attachment_refs": ["A001", "A001"]},
    ],
)
def test_invalid_or_unauthorized_capability_shape_rejected(change):
    with pytest.raises(ValidationError):
        Application.model_validate(application().model_dump() | change)


def test_canonical_hash_preserves_same_content_and_detects_changes():
    app = application()
    other = Application.model_validate(
        app.model_dump()
        | {
            "lines": [
                {"order_line_id": "L002", "quantity": 2},
                {"order_line_id": "L001", "quantity": 1},
            ],
            "attachment_refs": ["A002", "A001"],
        }
    )
    reordered = Application.model_validate(
        other.model_dump()
        | {
            "lines": list(reversed(other.model_dump()["lines"])),
            "attachment_refs": ["A001", "A002"],
        }
    )
    assert payload_hash(other, None, "v8", "v2") == payload_hash(reordered, None, "v8", "v2")
    baseline = payload_hash(app, None, "v8", "v2")
    assert baseline != payload_hash(app, None, "v9", "v2")
    assert baseline != payload_hash(app, Money(minor_units=1, currency="CNY"), "v8", "v2")
    changed = Application.model_validate(app.model_dump() | {"reason": "不同原因"})
    assert baseline != payload_hash(changed, None, "v8", "v2")


@pytest.mark.parametrize("tenant,actor", [("T002", "U001"), ("T001", "U002")])
def test_cross_identity_rejected(tenant, actor):
    rec = record()
    with pytest.raises(ValueError, match="ACCESS_DENIED"):
        check_binding(rec, submit(rec), tenant_id=tenant, actor_id=actor, now=NOW)


def test_expiry_boundary_and_changed_hash_rejected():
    rec = record()
    with pytest.raises(ValueError, match="CONFIRMATION_EXPIRED"):
        check_binding(rec, submit(rec), tenant_id="T001", actor_id="U001", now=rec.expires_at)
    wrong = PageSubmit.model_validate(submit(rec).model_dump() | {"payload_hash": "0" * 64})
    with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
        check_binding(rec, wrong, tenant_id="T001", actor_id="U001", now=NOW)


def test_used_record_returns_same_command_even_after_expiry_but_not_to_wrong_actor():
    used = PreflightRecord.model_validate(
        record().model_dump() | {"state": "USED", "command_id": "CMD001"}
    )
    assert (
        check_binding(
            used, submit(used), tenant_id="T001", actor_id="U001", now=NOW + timedelta(days=1)
        )
        == "CMD001"
    )
    with pytest.raises(ValueError, match="ACCESS_DENIED"):
        check_binding(used, submit(used), tenant_id="T001", actor_id="U002", now=NOW)


@pytest.mark.parametrize(
    "change", [{"confirmed": True}, {"tenant_id": "T002"}, {"actor_id": "U002"}]
)
def test_client_cannot_supply_server_identity_or_confirmation_boolean(change):
    with pytest.raises(ValidationError):
        PageSubmit.model_validate(submit(record()).model_dump() | change)


def test_chat_requires_workflow_confirmation_and_page_never_invents_conversation():
    with pytest.raises(ValidationError):
        ChatSubmit.model_validate(submit(record()).model_dump() | {"channel": "CHAT"})
    assert "conversation_id" not in PageSubmit.model_fields


@pytest.mark.parametrize(
    "change", [{"limit": 0}, {"limit": 101}, {"cursor": "x\ny"}, {"limit": True}]
)
def test_page_request_is_bounded(change):
    with pytest.raises(ValidationError):
        PageRequest.model_validate(change)


def test_page_response_cursor_consistency():
    PageReferences(items=["O001"], has_more=False, next_cursor=None)
    with pytest.raises(ValidationError):
        PageReferences(items=["O001"], has_more=True, next_cursor=None)


@pytest.mark.parametrize(
    "change",
    [
        {"command_status": "SUCCEEDED"},
        {"business_id": "B001"},
        {"next_action": "REVIEW_RESULT"},
        {"success": True},
    ],
)
def test_unknown_result_cannot_claim_business_success(change):
    data = {
        "command_id": "CMD001",
        "command_status": None,
        "observation": "RESULT_UNKNOWN",
        "reason_code": "COMMAND_RESULT_UNKNOWN",
        "business_id": None,
        "next_action": "QUERY_COMMAND",
    }
    CommandResult.model_validate(data)
    with pytest.raises(ValidationError):
        CommandResult.model_validate(data | change)


def test_preflight_rejects_changed_record_or_naive_expiry():
    for change in (
        {"payload_hash": "0" * 64},
        {"expires_at": datetime(2026, 9, 10)},
        {"state": "USED"},
    ):
        with pytest.raises(ValidationError):
            PreflightRecord.model_validate(record().model_dump() | change)


def test_nested_mutation_cannot_bypass_binding():
    rec = record()
    request = submit(rec)
    rec.application.attachment_refs.append("A002")
    with pytest.raises(ValidationError):
        check_binding(rec, request, tenant_id="T001", actor_id="U001", now=NOW)
