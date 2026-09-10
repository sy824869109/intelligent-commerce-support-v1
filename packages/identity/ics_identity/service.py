"""All session authority comes from current database state, never request identity claims."""

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import re
import secrets
from threading import BoundedSemaphore
from uuid import uuid4

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from ics_observability.audit import append_audit
from ics_observability.core import AuditRecord
from ics_persistence.identity_schema import (
    group_members,
    groups,
    login_buckets,
    memberships,
    organizations,
    permissions,
    role_permissions,
    roles,
    sessions,
    tenants,
    tokens,
    users,
    ROLE_GRANTS,
)
from .passwords import hash_password, verify_password

# Public authentication scheme, shared by token responses; never a credential.
AUTH_SCHEME = "Bearer"


class IdentityError(Exception):
    def __init__(self, code="AUTH_REQUIRED", status=401):
        self.code, self.status = code, status
        super().__init__(code)


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    session_id: str
    role: str


@dataclass(frozen=True)
class Resource:
    """Construct only from a trusted domain lookup, not JSON/path claims."""

    kind: str
    tenant_id: str
    owner_id: str | None = None
    group_id: str | None = None
    published: bool = False
    customer_visible: bool = False


def now(session):
    return session.scalar(select(func.current_timestamp())).replace(tzinfo=None)


def username(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", value):
        raise IdentityError("INPUT_INVALID", 422)
    return value


def token_digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
        raise IdentityError()
    return hashlib.sha256(value.encode()).hexdigest()


def seed_roles(session):
    # Used only during initial schema/bootstrap setup, never on ordinary login.
    for role in ROLE_GRANTS:
        session.execute(insert(roles).values(id=role))
    for permission in sorted({p for values in ROLE_GRANTS.values() for p in values}):
        session.execute(insert(permissions).values(id=permission))
    for role, grants in ROLE_GRANTS.items():
        for permission in grants:
            session.execute(insert(role_permissions).values(role_id=role, permission_id=permission))


def provision_tenant(session, *, organization_id, tenant_id, user_id, login, password_hash):
    """Operator-only bootstrap; caller validates target DB and obtains password interactively."""
    username(login)
    session.execute(insert(organizations).values(id=organization_id, name=organization_id))
    session.execute(
        insert(tenants).values(
            id=tenant_id, organization_id=organization_id, name=tenant_id, active=True
        )
    )
    session.execute(
        insert(users).values(id=user_id, username=login, password_hash=password_hash, active=True)
    )
    session.execute(
        insert(memberships).values(
            tenant_id=tenant_id, user_id=user_id, role_id="ADMIN", active=True
        )
    )


class Identity:
    def __init__(self, database):
        self.db = database
        self.hash_slots = BoundedSemaphore(2)
        # Unknown usernames undergo the same expensive check as known usernames.
        self.dummy = hash_password(secrets.token_urlsafe(24))

    def _principal(self, session, session_id):
        row = (
            session.execute(
                select(sessions, memberships.c.role_id)
                .join(
                    memberships,
                    (sessions.c.tenant_id == memberships.c.tenant_id)
                    & (sessions.c.user_id == memberships.c.user_id),
                )
                .join(users, users.c.id == sessions.c.user_id)
                .join(tenants, tenants.c.id == sessions.c.tenant_id)
                .where(
                    sessions.c.id == session_id,
                    sessions.c.revoked.is_(False),
                    sessions.c.expires_at > now(session),
                    memberships.c.active.is_(True),
                    users.c.active.is_(True),
                    tenants.c.active.is_(True),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise IdentityError()
        return Principal(row["user_id"], row["tenant_id"], session_id, row["role_id"])

    def _audit(self, session, principal, action, target):
        from datetime import timezone
        from ics_observability.core import CURRENT

        trace = CURRENT.get()
        # Event identity is unique; this is a committed mutation audit, not a request log.
        append_audit(
            session,
            AuditRecord(
                uuid4().hex,
                principal.user_id,
                principal.tenant_id,
                target,
                trace.request_id if trace else uuid4().hex,
                trace.trace_id if trace else uuid4().hex,
                action,
                "SUCCEEDED",
                now(session).replace(tzinfo=timezone.utc),
            ),
            tenant_ref=principal.tenant_id,
        )

    def _issue(self, session, session_id, absolute):
        current = now(session)
        result = {
            "token_type": AUTH_SCHEME,
            "expires_in": min(300, int((absolute - current).total_seconds())),
        }
        for kind, duration in (("ACCESS", timedelta(minutes=5)), ("REFRESH", timedelta(days=7))):
            raw = secrets.token_urlsafe(32)
            session.execute(
                insert(tokens).values(
                    digest=token_digest(raw),
                    session_id=session_id,
                    kind=kind,
                    expires_at=min(current + duration, absolute),
                    used=False,
                )
            )
            result[kind.lower() + "_token"] = raw
        return result

    def _rate(self, tenant_id, login, peer):
        # Persistent atomic buckets enforce limits across processes; never trust forwarded IP.
        with self.db.transaction() as session:
            current = now(session)
            expired = session.scalars(
                select(login_buckets.c.key).where(login_buckets.c.expires_at <= current).limit(100)
            ).all()
            if expired:
                session.execute(
                    delete(login_buckets).where(
                        login_buckets.c.key.in_(expired), login_buckets.c.expires_at <= current
                    )
                )
            for text, limit in (("peer:" + peer, 20), ("account:" + tenant_id + ":" + login, 5)):
                key = hashlib.sha256(text.encode()).hexdigest()
                try:
                    with session.begin_nested():
                        session.execute(
                            insert(login_buckets).values(
                                key=key, count=0, expires_at=current + timedelta(minutes=5)
                            )
                        )
                except IntegrityError:
                    # Concurrent insertion: lock and increment the winner's record below.
                    if (
                        session.scalar(
                            select(login_buckets.c.key).where(login_buckets.c.key == key)
                        )
                        is None
                    ):
                        raise
                row = (
                    session.execute(
                        select(login_buckets).where(login_buckets.c.key == key).with_for_update()
                    )
                    .mappings()
                    .one()
                )
                if row["count"] >= limit:
                    return False
                session.execute(
                    update(login_buckets)
                    .where(login_buckets.c.key == key)
                    .values(count=row["count"] + 1)
                )
        return True

    def login(self, tenant_id, login, password, peer):
        username(login)
        if not self._rate(tenant_id, login, peer) or not self.hash_slots.acquire(blocking=False):
            raise IdentityError("RATE_LIMITED", 429)
        try:
            with self.db.transaction() as session:
                user = (
                    session.execute(select(users).where(users.c.username == login))
                    .mappings()
                    .first()
                )
            valid = verify_password(password, user["password_hash"] if user else self.dummy)
            if not valid or not user:
                raise IdentityError()
            with self.db.transaction() as session:
                # Serialize with password changes and recheck the hash verified outside the transaction.
                current_user = (
                    session.execute(select(users).where(users.c.id == user["id"]).with_for_update())
                    .mappings()
                    .one()
                )
                member = (
                    session.execute(
                        select(memberships).where(
                            memberships.c.tenant_id == tenant_id,
                            memberships.c.user_id == user["id"],
                            memberships.c.active.is_(True),
                        )
                    )
                    .mappings()
                    .first()
                )
                tenant_active = session.scalar(
                    select(tenants.c.active).where(tenants.c.id == tenant_id)
                )
                if (
                    not current_user["active"]
                    or current_user["password_hash"] != user["password_hash"]
                    or not member
                    or not tenant_active
                ):
                    raise IdentityError()
                session_id, absolute = uuid4().hex, now(session) + timedelta(days=7)
                session.execute(
                    insert(sessions).values(
                        id=session_id,
                        user_id=user["id"],
                        tenant_id=tenant_id,
                        expires_at=absolute,
                        revoked=False,
                    )
                )
                result = self._issue(session, session_id, absolute)
                self._audit(
                    session,
                    Principal(user["id"], tenant_id, session_id, member["role_id"]),
                    "IDENTITY_LOGIN",
                    session_id,
                )
            return result
        finally:
            self.hash_slots.release()

    def authenticate(self, access_token):
        with self.db.transaction() as session:
            row = (
                session.execute(
                    select(tokens).where(
                        tokens.c.digest == token_digest(access_token),
                        tokens.c.kind == "ACCESS",
                        tokens.c.used.is_(False),
                        tokens.c.expires_at > now(session),
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise IdentityError()
            return self._principal(session, row["session_id"])

    def refresh(self, refresh_token):
        digest = token_digest(refresh_token)
        result = None
        with self.db.transaction() as session:
            row = (
                session.execute(
                    select(tokens).where(tokens.c.digest == digest, tokens.c.kind == "REFRESH")
                )
                .mappings()
                .first()
            )
            if row is None:
                raise IdentityError()
            locked = (
                session.execute(
                    select(sessions).where(sessions.c.id == row["session_id"]).with_for_update()
                )
                .mappings()
                .one()
            )
            principal = self._principal(session, locked["id"])
            # Re-read after the session lock so concurrent refreshes cannot both succeed.
            row = (
                session.execute(select(tokens).where(tokens.c.digest == digest).with_for_update())
                .mappings()
                .one()
            )
            if row["used"]:
                session.execute(
                    update(sessions).where(sessions.c.id == locked["id"]).values(revoked=True)
                )
                self._audit(session, principal, "IDENTITY_REVOKE", locked["id"])
                # Commit replay revocation before rejecting the request outside the transaction.
            elif row["expires_at"] <= now(session):
                raise IdentityError()
            else:
                self._refresh_budget(session, locked["id"])
                session.execute(
                    update(tokens).where(tokens.c.session_id == locked["id"]).values(used=True)
                )
                result = self._issue(session, locked["id"], locked["expires_at"])
                self._audit(session, principal, "IDENTITY_REFRESH", locked["id"])
        if result is None:
            raise IdentityError()
        return result

    def _refresh_budget(self, session, session_id):
        # Called under the session row lock, so one session cannot race this insert.
        key = hashlib.sha256(("refresh:" + session_id).encode()).hexdigest()
        current = now(session)
        row = (
            session.execute(
                select(login_buckets).where(login_buckets.c.key == key).with_for_update()
            )
            .mappings()
            .first()
        )
        if row is None:
            session.execute(
                insert(login_buckets).values(
                    key=key, count=1, expires_at=current + timedelta(minutes=5)
                )
            )
        elif row["expires_at"] <= current:
            session.execute(
                update(login_buckets)
                .where(login_buckets.c.key == key)
                .values(count=1, expires_at=current + timedelta(minutes=5))
            )
        elif row["count"] >= 30:
            raise IdentityError("RATE_LIMITED", 429)
        else:
            session.execute(
                update(login_buckets)
                .where(login_buckets.c.key == key)
                .values(count=row["count"] + 1)
            )

    def prune_expired(self, limit=100):
        """Bounded operator maintenance; only expired sessions/tokens, never audit history."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid maintenance batch")
        with self.db.transaction() as session:
            expired = session.scalars(
                select(sessions.c.id)
                .where(sessions.c.expires_at <= now(session))
                .limit(limit)
                .with_for_update()
            ).all()
            if expired:
                session.execute(delete(tokens).where(tokens.c.session_id.in_(expired)))
                session.execute(delete(sessions).where(sessions.c.id.in_(expired)))
        return len(expired)

    def logout(self, principal):
        with self.db.transaction() as session:
            current = self._principal(session, principal.session_id)
            session.execute(
                update(sessions).where(sessions.c.id == current.session_id).values(revoked=True)
            )
            self._audit(session, current, "IDENTITY_REVOKE", current.session_id)

    def authorize(self, session, principal, action, resource):
        current = self._principal(session, principal.session_id)
        allowed = session.scalar(
            select(role_permissions.c.permission_id).where(
                role_permissions.c.role_id == current.role,
                role_permissions.c.permission_id == action,
            )
        )
        if (
            not allowed
            or resource.tenant_id != current.tenant_id
            or action.split(".")[0] != resource.kind
        ):
            raise IdentityError("ACCESS_DENIED", 404)
        if current.role == "ADMIN":
            return current
        if resource.kind == "knowledge":
            if not resource.published:
                raise IdentityError("ACCESS_DENIED", 404)
            if resource.customer_visible:
                return current
        elif current.role == "CUSTOMER" and resource.owner_id == current.user_id:
            return current
        if (
            current.role == "AGENT"
            and resource.group_id
            and session.scalar(
                select(group_members.c.user_id).where(
                    group_members.c.tenant_id == current.tenant_id,
                    group_members.c.user_id == current.user_id,
                    group_members.c.group_id == resource.group_id,
                )
            )
        ):
            return current
        raise IdentityError("ACCESS_DENIED", 404)

    def change_password(self, principal, old_password, new_password):
        if old_password == new_password:
            raise ValueError("New password must differ")
        if not self._rate("password-change", principal.user_id, principal.session_id):
            raise IdentityError("RATE_LIMITED", 429)
        if not self.hash_slots.acquire(blocking=False):
            raise IdentityError("RATE_LIMITED", 429)
        try:
            with self.db.transaction() as session:
                current = self._principal(session, principal.session_id)
                encoded = session.scalar(
                    select(users.c.password_hash).where(users.c.id == current.user_id)
                )
            if not verify_password(old_password, encoded):
                raise IdentityError()
            replacement = hash_password(new_password)
            with self.db.transaction() as session:
                self._principal(session, principal.session_id)
                locked = session.scalar(
                    select(users.c.password_hash)
                    .where(users.c.id == current.user_id)
                    .with_for_update()
                )
                if locked != encoded:
                    raise IdentityError()
                session.execute(
                    update(users)
                    .where(users.c.id == current.user_id)
                    .values(password_hash=replacement)
                )
                session.execute(
                    update(sessions)
                    .where(sessions.c.user_id == current.user_id)
                    .values(revoked=True)
                )
                self._audit(session, current, "IDENTITY_PASSWORD", current.user_id)
        finally:
            self.hash_slots.release()

    def update_member(self, principal, user_id, role, active):
        with self.db.transaction() as session:
            # Tenant lock serializes last-admin checks and tenant-scoped role mutations.
            session.execute(
                select(tenants.c.id).where(tenants.c.id == principal.tenant_id).with_for_update()
            ).one()
            current = self.authorize(
                session, principal, "identity.manage", Resource("identity", principal.tenant_id)
            )
            member = (
                session.execute(
                    select(memberships)
                    .where(
                        memberships.c.tenant_id == current.tenant_id,
                        memberships.c.user_id == user_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if member is None:
                raise IdentityError("ACCESS_DENIED", 404)
            if role not in ROLE_GRANTS or type(active) is not bool:
                raise IdentityError("INPUT_INVALID", 422)
            if (
                member["role_id"] == "ADMIN"
                and member["active"]
                and (role != "ADMIN" or not active)
            ):
                admins = session.scalar(
                    select(func.count())
                    .select_from(memberships)
                    .join(users, users.c.id == memberships.c.user_id)
                    .where(
                        memberships.c.tenant_id == current.tenant_id,
                        memberships.c.role_id == "ADMIN",
                        memberships.c.active.is_(True),
                        users.c.active.is_(True),
                    )
                )
                if admins <= 1:
                    raise IdentityError("LAST_ADMIN", 409)
            session.execute(
                update(memberships)
                .where(
                    memberships.c.tenant_id == current.tenant_id, memberships.c.user_id == user_id
                )
                .values(role_id=role, active=active)
            )
            session.execute(
                update(sessions)
                .where(sessions.c.tenant_id == current.tenant_id, sessions.c.user_id == user_id)
                .values(revoked=True)
            )
            self._audit(session, current, "IDENTITY_MEMBER", user_id)

    def create_member(self, principal, login, password, role):
        username(login)
        with self.db.transaction() as session:
            self.authorize(
                session, principal, "identity.manage", Resource("identity", principal.tenant_id)
            )
        if role not in ROLE_GRANTS:
            raise IdentityError("INPUT_INVALID", 422)
        if not self.hash_slots.acquire(blocking=False):
            raise IdentityError("RATE_LIMITED", 429)
        try:
            encoded = hash_password(password)
        finally:
            self.hash_slots.release()
        user_id = uuid4().hex
        try:
            with self.db.transaction() as session:
                current = self.authorize(
                    session, principal, "identity.manage", Resource("identity", principal.tenant_id)
                )
                session.execute(
                    insert(users).values(
                        id=user_id, username=login, password_hash=encoded, active=True
                    )
                )
                session.execute(
                    insert(memberships).values(
                        tenant_id=current.tenant_id, user_id=user_id, role_id=role, active=True
                    )
                )
                self._audit(session, current, "IDENTITY_MEMBER", user_id)
        except IntegrityError:
            raise IdentityError("ACCOUNT_CONFLICT", 409) from None
        return user_id

    def create_group(self, principal, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise IdentityError("INPUT_INVALID", 422)
        with self.db.transaction() as session:
            current = self.authorize(
                session, principal, "identity.manage", Resource("identity", principal.tenant_id)
            )
            group_id = uuid4().hex
            session.execute(
                insert(groups).values(tenant_id=current.tenant_id, id=group_id, name=name)
            )
            self._audit(session, current, "IDENTITY_MEMBER", group_id)
        return group_id

    def group_member(self, principal, group_id, user_id, active):
        if type(active) is not bool:
            raise IdentityError("INPUT_INVALID", 422)
        with self.db.transaction() as session:
            session.execute(
                select(tenants.c.id).where(tenants.c.id == principal.tenant_id).with_for_update()
            ).one()
            current = self.authorize(
                session, principal, "identity.manage", Resource("identity", principal.tenant_id)
            )
            if not session.scalar(
                select(groups.c.id).where(
                    groups.c.tenant_id == current.tenant_id, groups.c.id == group_id
                )
            ):
                raise IdentityError("ACCESS_DENIED", 404)
            if not session.scalar(
                select(memberships.c.user_id).where(
                    memberships.c.tenant_id == current.tenant_id,
                    memberships.c.user_id == user_id,
                    memberships.c.active.is_(True),
                    memberships.c.role_id.in_(["AGENT", "ADMIN"]),
                )
            ):
                raise IdentityError("ACCESS_DENIED", 404)
            condition = (
                (group_members.c.tenant_id == current.tenant_id)
                & (group_members.c.group_id == group_id)
                & (group_members.c.user_id == user_id)
            )
            session.execute(delete(group_members).where(condition))
            if active:
                session.execute(
                    insert(group_members).values(
                        tenant_id=current.tenant_id, group_id=group_id, user_id=user_id
                    )
                )
            self._audit(session, current, "IDENTITY_MEMBER", group_id)
