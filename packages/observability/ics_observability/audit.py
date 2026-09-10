"""Transactional audit sink using the existing platform database, no independent commit."""

from dataclasses import asdict
import hashlib

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from ics_persistence.database import require_transaction
from ics_persistence.schema import audit
from .core import AuditRecord


class AuditConflict(Exception):
    """An existing tenant/event identity has different content; no content is exposed."""


def append_audit(session, record: AuditRecord, *, tenant_ref: str) -> bool:
    """Return True for insertion, False for an identical retry, never a commit receipt.

    Caller must not suppress errors: its owner transaction rolls back business and
    audit together. Call only after authentication with a trusted tenant reference.
    """
    require_transaction(session)
    record = AuditRecord(**asdict(record))
    if record.tenant_ref != tenant_ref:
        raise ValueError("Audit tenant mismatch")
    raw = record.to_json()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    try:
        with session.begin_nested():
            session.execute(
                insert(audit).values(
                    tenant_ref=tenant_ref,
                    event_id=record.event_id,
                    record_json=raw,
                    record_hash=digest,
                )
            )
        return True
    except IntegrityError:
        previous = session.execute(
            select(audit.c.record_json, audit.c.record_hash).where(
                audit.c.tenant_ref == tenant_ref, audit.c.event_id == record.event_id
            )
        ).first()
        if previous is None:
            raise
        if previous.record_json != raw or previous.record_hash != digest:
            raise AuditConflict("Audit identity conflict") from None
        return False
