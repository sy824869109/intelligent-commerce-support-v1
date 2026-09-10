"""M03 live HTTP and synthetic resource authorization; never seed real accounts."""

from dataclasses import replace
from datetime import timedelta
import logging

from fastapi import Depends
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, insert, select, update
from sqlalchemy.pool import StaticPool

from ics_gateway.app import create_app
from ics_gateway.identity import require_resource
from ics_identity.passwords import hash_password, verify_password, validate_password
from ics_identity.service import Identity, IdentityError, Resource, now, provision_tenant
from ics_persistence.database import Database
from ics_persistence.migration import migrate
from ics_persistence.identity_schema import (
    users,
    memberships,
    sessions,
    tokens,
    tenants,
    groups,
    group_members,
    login_buckets,
)
from ics_persistence.schema import audit

PASSWORD = "Synthetic-Only-Password-47!"


@pytest.fixture(scope="module")
def encoded():
    return hash_password(PASSWORD)


@pytest.fixture
def identity(encoded):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False, "autocommit": False},
        poolclass=StaticPool,
    )
    database = Database(engine)
    migrate(engine)
    with database.transaction() as session:
        for suffix in ("A", "B"):
            provision_tenant(
                session,
                organization_id="ORG" + suffix,
                tenant_id=suffix,
                user_id="ADMIN" + suffix,
                login="admin" + suffix.lower(),
                password_hash=encoded,
            )
        for uid, role in (("CUSTOMER", "CUSTOMER"), ("OTHER", "CUSTOMER"), ("AGENT", "AGENT")):
            session.execute(
                insert(users).values(
                    id=uid, username=uid.lower(), password_hash=encoded, active=True
                )
            )
            session.execute(
                insert(memberships).values(tenant_id="A", user_id=uid, role_id=role, active=True)
            )
        session.execute(insert(groups).values(tenant_id="A", id="G1", name="group1"))
        session.execute(insert(group_members).values(tenant_id="A", group_id="G1", user_id="AGENT"))
    service = Identity(database)
    yield service
    database.close()


def login(service, name="customer", tenant="A"):
    return service.login(tenant, name, PASSWORD, "127.0.0.1")


def bearer(pair):
    return {"Authorization": "Bearer " + pair["access_token"]}


def test_password_hash_and_policy(encoded):
    assert encoded.startswith("scrypt-v1$") and PASSWORD not in encoded
    assert verify_password(PASSWORD, encoded)
    assert not verify_password("Wrong-Synthetic-Password!", encoded)
    for value in ("short", "a" * 20, "x" * 129, "passwordpassword"):
        with pytest.raises(ValueError):
            validate_password(value)
    assert not verify_password(PASSWORD, "invalid")


def test_login_refresh_replay_revokes_whole_session(identity):
    first = login(identity)
    assert identity.authenticate(first["access_token"]).role == "CUSTOMER"
    with identity.db.transaction() as session:
        persisted = str(session.execute(select(tokens)).all())
        assert first["access_token"] not in persisted and first["refresh_token"] not in persisted
    second = identity.refresh(first["refresh_token"])
    with pytest.raises(IdentityError):
        identity.authenticate(first["access_token"])
    assert identity.authenticate(second["access_token"]).tenant_id == "A"
    with pytest.raises(IdentityError):
        identity.refresh(first["refresh_token"])
    with pytest.raises(IdentityError):
        identity.authenticate(second["access_token"])
    with pytest.raises(IdentityError):
        identity.refresh(second["refresh_token"])


def test_logout_password_change_and_expiry(identity):
    first = login(identity)
    principal = identity.authenticate(first["access_token"])
    identity.logout(principal)
    with pytest.raises(IdentityError):
        identity.authenticate(first["access_token"])
    second, third = login(identity), login(identity)
    identity.change_password(
        identity.authenticate(second["access_token"]), PASSWORD, "New-Synthetic-Passphrase-49!"
    )
    for pair in (second, third):
        with pytest.raises(IdentityError):
            identity.authenticate(pair["access_token"])
    with pytest.raises(IdentityError):
        login(identity)
    pair = identity.login("A", "customer", "New-Synthetic-Passphrase-49!", "different-ip")
    with identity.db.transaction() as session:
        session.execute(update(sessions).values(expires_at=now(session) - timedelta(seconds=1)))
    with pytest.raises(IdentityError):
        identity.authenticate(pair["access_token"])


@pytest.mark.parametrize(
    "role,uid", [("CUSTOMER", "CUSTOMER"), ("AGENT", "AGENT"), ("ADMIN", "ADMINA")]
)
@pytest.mark.parametrize("kind", ["order", "ticket", "knowledge"])
def test_tenant_and_resource_matrix(identity, role, uid, kind):
    pair = login(identity, uid.lower())
    principal = identity.authenticate(pair["access_token"])
    with identity.db.transaction() as session:
        own = Resource(
            kind, "A", owner_id=uid, group_id="G1", published=True, customer_visible=True
        )
        assert identity.authorize(session, principal, kind + ".read", own).role == role
        with pytest.raises(IdentityError) as denial:
            identity.authorize(session, principal, kind + ".read", replace(own, tenant_id="B"))
        assert denial.value.status == 404
        private = Resource(kind, "A", owner_id="OTHER", group_id="OTHER_GROUP")
        if role == "ADMIN":
            identity.authorize(session, principal, kind + ".read", private)
        else:
            with pytest.raises(IdentityError):
                identity.authorize(session, principal, kind + ".read", private)
        if role != "ADMIN":
            with pytest.raises(IdentityError):
                identity.authorize(
                    session,
                    replace(principal, role="ADMIN"),
                    "knowledge.publish",
                    Resource("knowledge", "A"),
                )


def test_live_permission_changes_and_last_admin(identity):
    admin = identity.authenticate(login(identity, "admina")["access_token"])
    agent_pair = login(identity, "agent")
    agent = identity.authenticate(agent_pair["access_token"])
    identity.group_member(admin, "G1", "AGENT", False)
    with identity.db.transaction() as session:
        with pytest.raises(IdentityError):
            identity.authorize(
                session, agent, "ticket.reply", Resource("ticket", "A", group_id="G1")
            )
    identity.update_member(admin, "AGENT", "CUSTOMER", True)
    with pytest.raises(IdentityError):
        identity.authenticate(agent_pair["access_token"])
    with pytest.raises(IdentityError) as exc:
        identity.update_member(admin, "ADMINA", "CUSTOMER", False)
    assert exc.value.code == "LAST_ADMIN"
    with pytest.raises(IdentityError):
        identity.update_member(admin, "ADMINB", "CUSTOMER", False)


def test_rate_limit_persists_and_unknown_identity(identity):
    for _ in range(5):
        with pytest.raises(IdentityError) as exc:
            identity.login("A", "unknown", PASSWORD, "peer")
        assert exc.value.status == 401
    second = Identity(identity.db)
    with pytest.raises(IdentityError) as exc:
        second.login("A", "unknown", PASSWORD, "other-peer")
    assert exc.value.status == 429
    with identity.db.transaction() as session:
        assert len(session.execute(select(login_buckets)).all()) >= 2


def test_http_boundary_and_protected_domain_dependencies(identity, caplog):
    app = create_app(identity=identity)
    resource = Resource("order", "A", owner_id="CUSTOMER")

    @app.get("/api/testing/orders/{order_id}")
    def order(principal=Depends(require_resource("order.read", lambda s, r, p: resource))):
        return {"authorized": True}

    with TestClient(app) as client, caplog.at_level(logging.INFO, logger="ics.gateway.requests"):
        data = {"tenant_id": "A", "username": "customer", "password": PASSWORD}
        result = client.post("/api/v1/auth/login", json=data)
        assert result.status_code == 200
        pair = result.json()["data"]
        assert result.headers["cache-control"] == "no-store"
        assert "set-cookie" not in result.headers
        assert (
            client.get("/api/v1/auth/me", headers=bearer(pair)).json()["data"]["user_id"]
            == "CUSTOMER"
        )
        assert client.get("/api/testing/orders/O1", headers=bearer(pair)).status_code == 200
        resource = replace(resource, owner_id="OTHER")
        assert (
            client.get(
                "/api/testing/orders/O1",
                headers=bearer(pair) | {"X-Role": "ADMIN", "X-Tenant-ID": "B"},
            ).status_code
            == 404
        )
        assert (
            client.get(
                "/api/v1/auth/me", headers={"Cookie": "access_token=" + pair["access_token"]}
            ).status_code
            == 401
        )
        assert client.get("/api/v1/auth/me?access_token=" + pair["access_token"]).status_code == 400
        assert (
            client.post(
                "/api/v1/auth/login", json=data, headers={"Origin": "https://evil.invalid"}
            ).status_code
            == 403
        )
        assert client.post("/api/v1/auth/login", json=data | {"role": "ADMIN"}).status_code == 422
        assert (
            client.post(
                "/api/v1/auth/login",
                content="x" * 5000,
                headers={"Content-Type": "application/json"},
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/api/v1/auth/login",
                content='{"username":"a","username":"b"}',
                headers={"Content-Type": "application/json"},
            ).status_code
            == 422
        )
        assert client.post("/api/v1/auth/logout", json={}, headers=bearer(pair)).status_code == 200
        assert client.get("/api/v1/auth/me", headers=bearer(pair)).status_code == 401
    assert PASSWORD not in caplog.text and pair["access_token"] not in caplog.text


def test_http_admin_create_and_no_cross_tenant_mutation(identity):
    app = create_app(identity=identity)
    admin, customer = login(identity, "admina"), login(identity)
    with TestClient(app) as client:
        body = {"username": "newcustomer", "password": PASSWORD, "role": "CUSTOMER"}
        assert (
            client.post("/api/v1/auth/members", json=body, headers=bearer(customer)).status_code
            == 404
        )
        response = client.post("/api/v1/auth/members", json=body, headers=bearer(admin))
        assert response.status_code == 201
        uid = response.json()["data"]["id"]
        assert (
            client.patch(
                "/api/v1/auth/members/ADMINB",
                json={"role": "AGENT", "active": False},
                headers=bearer(admin),
            ).status_code
            == 404
        )
        assert (
            client.patch(
                "/api/v1/auth/members/" + uid,
                json={"role": "CUSTOMER", "active": False},
                headers=bearer(admin),
            ).status_code
            == 200
        )
    with identity.db.transaction() as session:
        assert session.execute(select(audit)).first() is not None


def test_disabled_tenant_and_user_fail_closed(identity):
    pair = login(identity)
    with identity.db.transaction() as session:
        session.execute(update(tenants).where(tenants.c.id == "A").values(active=False))
    with pytest.raises(IdentityError):
        identity.authenticate(pair["access_token"])


def test_audit_failure_rolls_back_login(identity, monkeypatch):
    def unavailable(*args):
        raise RuntimeError("Audit unavailable")

    monkeypatch.setattr(identity, "_audit", unavailable)
    with pytest.raises(RuntimeError):
        login(identity)
    with identity.db.transaction() as session:
        assert session.execute(select(sessions)).first() is None


def test_wrong_tenant_disabled_user_and_token_kind(identity):
    with pytest.raises(IdentityError):
        login(identity, tenant="B")
    pair = login(identity)
    with pytest.raises(IdentityError):
        identity.authenticate(pair["refresh_token"])
    with pytest.raises(IdentityError):
        identity.refresh(pair["access_token"])
    with identity.db.transaction() as session:
        session.execute(update(users).where(users.c.id == "CUSTOMER").values(active=False))
    with pytest.raises(IdentityError):
        identity.authenticate(pair["access_token"])


def test_invalid_bearer_duplicates_and_origin_configuration(identity):
    from ics_gateway.settings import Settings
    from pydantic import ValidationError

    with TestClient(create_app(identity=identity)) as client:
        pair = login(identity)
        assert (
            client.get(
                "/api/v1/auth/me",
                headers=[
                    ("Authorization", "Bearer " + pair["access_token"]),
                    ("Authorization", "Bearer invalid"),
                ],
            ).status_code
            == 401
        )
        assert (
            client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid"}).status_code
            == 401
        )
        assert client.post("/api/v1/auth/login", content="text/plain").status_code == 415
    for origin in (
        "*",
        "http://evil.invalid",
        "https://user:pass@example.com",
        "https://example.com/path",
    ):
        with pytest.raises(ValidationError):
            Settings(allowed_origins=(origin,))


@pytest.mark.parametrize("kind", ["order", "ticket", "knowledge"])
def test_http_resource_permission_matrix(identity, kind):
    from sqlalchemy import Boolean, Column, MetaData, String, Table

    table = Table(
        "synthetic_resources",
        MetaData(),
        Column("id", String, primary_key=True),
        Column("kind", String),
        Column("tenant_id", String),
        Column("owner_id", String),
        Column("group_id", String),
        Column("published", Boolean),
        Column("customer_visible", Boolean),
    )
    table.create(identity.db.engine)
    with identity.db.transaction() as session:
        session.execute(
            insert(table),
            [
                dict(
                    id="own",
                    kind=kind,
                    tenant_id="A",
                    owner_id="CUSTOMER",
                    group_id="G1",
                    published=True,
                    customer_visible=True,
                ),
                dict(
                    id="cross",
                    kind=kind,
                    tenant_id="B",
                    owner_id="CUSTOMER",
                    group_id="G1",
                    published=True,
                    customer_visible=True,
                ),
                dict(
                    id="private",
                    kind=kind,
                    tenant_id="A",
                    owner_id="OTHER",
                    group_id="G2",
                    published=False,
                    customer_visible=False,
                ),
            ],
        )

    def load(session, request, principal):
        row = (
            session.execute(select(table).where(table.c.id == request.path_params["resource_id"]))
            .mappings()
            .first()
        )
        return (
            Resource(**{key: value for key, value in row.items() if key != "id"}) if row else None
        )

    app = create_app(identity=identity)

    @app.get("/api/testing/resources/{resource_id}")
    def resource(principal=Depends(require_resource(kind + ".read", load))):
        return {"permitted": True}

    with TestClient(app) as client:
        for account in ("customer", "agent", "admina"):
            headers = bearer(login(identity, account))
            assert client.get("/api/testing/resources/own", headers=headers).status_code == 200
            assert client.get("/api/testing/resources/cross", headers=headers).status_code == 404
            assert client.get("/api/testing/resources/missing", headers=headers).status_code == 404
            assert client.get("/api/testing/resources/private", headers=headers).status_code == (
                200 if account == "admina" else 404
            )


def test_refresh_limit_expiry_and_bounded_cleanup(identity):
    import hashlib

    pair = login(identity)
    principal = identity.authenticate(pair["access_token"])
    key = hashlib.sha256(("refresh:" + principal.session_id).encode()).hexdigest()
    with identity.db.transaction() as session:
        session.execute(
            insert(login_buckets).values(
                key=key, count=30, expires_at=now(session) + timedelta(minutes=5)
            )
        )
    with pytest.raises(IdentityError) as exc:
        identity.refresh(pair["refresh_token"])
    assert exc.value.status == 429
    assert identity.authenticate(pair["access_token"]).user_id == "CUSTOMER"
    with identity.db.transaction() as session:
        session.execute(update(sessions).values(expires_at=now(session) - timedelta(seconds=1)))
    assert identity.prune_expired() == 1
    with identity.db.transaction() as session:
        assert session.execute(select(tokens)).first() is None
        assert session.execute(select(audit)).first() is not None


def test_http_group_refresh_and_password_lifecycle(identity):
    with TestClient(create_app(identity=identity)) as client:
        admin_headers = bearer(login(identity, "admina"))
        created = client.post(
            "/api/v1/auth/members",
            json={"username": "httpagent", "password": PASSWORD, "role": "AGENT"},
            headers=admin_headers,
        )
        assert created.status_code == 201
        user_id = created.json()["data"]["id"]
        group = client.post(
            "/api/v1/auth/groups", json={"name": "http-group"}, headers=admin_headers
        )
        assert group.status_code == 201
        group_id = group.json()["data"]["id"]
        assert (
            client.put(
                "/api/v1/auth/groups/" + group_id + "/members",
                json={"user_id": user_id, "active": True},
                headers=admin_headers,
            ).status_code
            == 200
        )
        logged = client.post(
            "/api/v1/auth/login",
            json={"tenant_id": "A", "username": "httpagent", "password": PASSWORD},
        )
        assert logged.status_code == 200
        pair = logged.json()["data"]
        refreshed = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        )
        assert refreshed.status_code == 200
        new_pair = refreshed.json()["data"]
        assert client.get("/api/v1/auth/me", headers=bearer(pair)).status_code == 401
        changed = client.post(
            "/api/v1/auth/password",
            json={"old_password": PASSWORD, "new_password": "Changed-HTTP-Passphrase-82!"},
            headers=bearer(new_pair),
        )
        assert changed.status_code == 200
        assert client.get("/api/v1/auth/me", headers=bearer(new_pair)).status_code == 401
