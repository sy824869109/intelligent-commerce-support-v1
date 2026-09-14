"""同一组真实 HTTP/SQL 用例在 SQLite 单测与专用 MySQL 临时容器中执行。"""

from datetime import datetime, timedelta, timezone
from dataclasses import replace
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, delete, insert, update
from sqlalchemy.pool import StaticPool

from ics_commerce.catalog import Catalog
from ics_gateway.app import create_app
from ics_identity.passwords import hash_password
from ics_identity.service import Identity, IdentityError, provision_tenant
from ics_persistence import commerce_schema as t
from ics_persistence.database import Database, DatabaseConfig
from ics_persistence.identity_schema import memberships, role_permissions, sessions, users
from ics_persistence.migration import migrate

PASSWORD = "Synthetic-Catalog-Password-73!"
CURRENT = datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def password_hash():
    return hash_password(PASSWORD)


@pytest.fixture
def catalog(password_hash):
    if "ICS_TEST_MYSQL_PORT" in os.environ:
        db = Database.connect(
            DatabaseConfig(
                username="ics_m02_test",
                password=os.environ["ICS_TEST_MYSQL_PASSWORD"],
                database="ics_m02_test",
                port=int(os.environ["ICS_TEST_MYSQL_PORT"]),
            )
        )
    else:
        db = Database(
            create_engine(
                "sqlite://",
                poolclass=StaticPool,
                connect_args={"check_same_thread": False, "autocommit": False},
            )
        )
    migrate(db.engine)
    marker = uuid4().hex
    tenant = marker + "A"
    other = marker + "B"
    observed = dict(
        source="synthetic",
        source_version=1,
        as_of=CURRENT.replace(tzinfo=None),
        synced_at=CURRENT.replace(tzinfo=None),
    )
    with db.transaction() as session:
        for scope in (tenant, other):
            provision_tenant(
                session,
                organization_id=scope,
                tenant_id=scope,
                user_id=scope,
                login="admin" + scope.lower(),
                password_hash=password_hash,
            )
            session.execute(
                insert(t.categories).values(tenant_id=scope, id="C1", name="耳机", **observed)
            )
            for pid, status in (("P1", "ON_SALE"), ("P2", "ON_SALE"), ("HIDDEN", "DRAFT")):
                session.execute(
                    insert(t.products).values(
                        tenant_id=scope,
                        id=pid,
                        category_id="C1",
                        name=("甲店" if scope == tenant else "乙店")
                        + "耳机"
                        + ("100%" if pid == "P2" else ""),
                        description="合成数据，不是实际商品",
                        status=status,
                        **observed,
                    )
                )
            for sid, quantity in (("BLACK", 12), ("WHITE", None), ("EMPTY", 0), ("MISSING", None)):
                session.execute(
                    insert(t.skus).values(
                        tenant_id=scope,
                        id=sid,
                        product_id="P1",
                        code=sid,
                        specifications=[["颜色", sid]],
                        status="ON_SALE",
                        **observed,
                    )
                )
                if sid != "MISSING":
                    session.execute(
                        insert(t.inventory).values(
                            tenant_id=scope, sku_id=sid, available_quantity=quantity, **observed
                        )
                    )
                    session.execute(
                        insert(t.prices).values(
                            tenant_id=scope,
                            sku_id=sid,
                            minor_units=29900,
                            currency="CNY",
                            valid_from=CURRENT.replace(tzinfo=None),
                            **observed,
                        )
                    )
            session.execute(
                insert(t.attributes).values(
                    tenant_id=scope,
                    product_id="P1",
                    name="续航",
                    value="30",
                    unit="小时",
                    **observed,
                )
            )
        for role in ("CUSTOMER", "AGENT"):
            uid = marker + role
            session.execute(
                insert(users).values(
                    id=uid, username=uid.lower(), password_hash=password_hash, active=True
                )
            )
            session.execute(
                insert(memberships).values(tenant_id=tenant, user_id=uid, role_id=role, active=True)
            )
    identity = Identity(db)
    service = Catalog(identity, clock=lambda: CURRENT)
    service.test_tenant, service.test_other, service.test_marker = tenant, other, marker
    yield service
    db.close()


def credentials(catalog, role="CUSTOMER", other=False):
    tenant = catalog.test_other if other else catalog.test_tenant
    name = ("admin" + tenant if role == "ADMIN" else catalog.test_marker + role).lower()
    pair = catalog.identity.login(tenant, name, PASSWORD, "synthetic-peer-" + catalog.test_marker)
    return {"Authorization": "Bearer " + pair["access_token"]}


def client(catalog):
    return TestClient(create_app(identity=catalog.identity, catalog=catalog))


@pytest.mark.parametrize("role", ["CUSTOMER", "AGENT", "ADMIN"])
def test_authorized_full_query_flow(catalog, role):
    with client(catalog) as http:
        login = (
            "admin" + catalog.test_tenant if role == "ADMIN" else catalog.test_marker + role
        ).lower()
        signed_in = http.post(
            "/api/v1/auth/login",
            json={
                "tenant_id": catalog.test_tenant,
                "username": login,
                "password": PASSWORD,
            },
        )
        assert signed_in.status_code == 200
        headers = {"Authorization": "Bearer " + signed_in.json()["data"]["access_token"]}
        response = http.get("/api/v1/products?q=耳机&limit=1", headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        first = response.json()["data"]
        assert first["items"][0]["id"] == "P1" and first["has_more"]
        second = http.get("/api/v1/products?after=P1&limit=1", headers=headers).json()["data"]
        assert second["items"][0]["id"] == "P2" and not second["has_more"]
        detail = http.get("/api/v1/products/P1", headers=headers).json()["data"]
        assert detail["category"]["name"] == "耳机" and "甲店" in detail["name"]
        assert detail["observation"]["source_version"] == "1"
        specs = http.get("/api/v1/products/P1/specifications?limit=2", headers=headers).json()[
            "data"
        ]
        assert len(specs["items"]) == 2 and specs["has_more"]
        assert specs["attributes"][0]["name"] == "续航"
        facts = http.get("/api/v1/products/P1/skus/BLACK", headers=headers).json()["data"]
        assert facts["price"]["minor_units"] == 29900 and facts["price_state"] == "AVAILABLE"
        assert facts["inventory_state"] == "IN_STOCK" and not facts["stock_reserved"]
        activity = http.get("/api/v1/products/P1/activity", headers=headers).json()["data"]
        assert activity["state"] == "UNKNOWN" and activity["source"] is None


@pytest.mark.parametrize(
    "path", ["", "/P1", "/P1/specifications", "/P1/skus/BLACK", "/P1/activity"]
)
def test_anonymous_denied(catalog, path):
    with client(catalog) as http:
        response = http.get("/api/v1/products" + path)
        assert response.status_code == 401


@pytest.mark.parametrize(
    "query",
    [
        "tenant_id=B",
        "limit=0",
        "limit=101",
        "limit=1&limit=2",
        "q=%00",
        "after=bad!",
        "actor_id=other",
    ],
)
def test_reject_scope_and_ambiguous_query(catalog, query):
    with client(catalog) as http:
        assert (
            http.get("/api/v1/products?" + query, headers=credentials(catalog)).status_code == 422
        )


def test_tenant_hidden_wrong_product_and_literal_search(catalog):
    with client(catalog) as http:
        headers = credentials(catalog)
        assert "乙店" not in http.get("/api/v1/products", headers=headers).text
        for path in ("/HIDDEN", "/ABSENT", "/P2/skus/BLACK", "/HIDDEN/activity"):
            assert http.get("/api/v1/products" + path, headers=headers).status_code == 404
        body = http.get("/api/v1/products?q=%25", headers=headers).json()["data"]
        assert [row["id"] for row in body["items"]] == ["P2"]
        other = credentials(catalog, "ADMIN", other=True)
        assert "乙店" in http.get("/api/v1/products/P1", headers=other).json()["data"]["name"]


@pytest.mark.parametrize(
    "sid,state", [("WHITE", "UNKNOWN"), ("EMPTY", "OUT_OF_STOCK"), ("MISSING", "UNKNOWN")]
)
def test_missing_vs_zero(catalog, sid, state):
    with client(catalog) as http:
        body = http.get("/api/v1/products/P1/skus/" + sid, headers=credentials(catalog)).json()[
            "data"
        ]
        assert body["inventory_state"] == state
        if sid == "MISSING":
            assert (
                body["price"] is None
                and body["inventory"] is None
                and body["price_state"] == "UNKNOWN"
            )


@pytest.mark.parametrize("offset,state", [(-301, "STALE"), (1, "FUTURE")])
def test_source_time_not_sync_time(catalog, offset, state):
    with catalog.identity.db.transaction() as session:
        stamp = (CURRENT + timedelta(seconds=offset)).replace(tzinfo=None)
        for table in (t.prices, t.inventory):
            session.execute(
                update(table)
                .where(table.c.tenant_id == catalog.test_tenant)
                .values(as_of=stamp, synced_at=max(stamp, CURRENT.replace(tzinfo=None)))
            )
    with client(catalog) as http:
        body = http.get("/api/v1/products/P1/skus/BLACK", headers=credentials(catalog)).json()[
            "data"
        ]
        assert body["price_state"] == state and body["inventory_state"] == state


@pytest.mark.parametrize("window,state", [("expired", "EXPIRED"), ("future", "NOT_STARTED")])
def test_price_window(catalog, window, state):
    current = CURRENT.replace(tzinfo=None)
    values = (
        dict(valid_from=current - timedelta(hours=1), valid_until=current)
        if window == "expired"
        else dict(valid_from=current + timedelta(hours=1))
    )
    with catalog.identity.db.transaction() as session:
        session.execute(
            update(t.prices).where(t.prices.c.tenant_id == catalog.test_tenant).values(**values)
        )
    with client(catalog) as http:
        body = http.get("/api/v1/products/P1/skus/BLACK", headers=credentials(catalog)).json()[
            "data"
        ]
        assert body["price_state"] == state


def test_revoked_session_and_permission_denied(catalog):
    headers = credentials(catalog)
    principal = catalog.identity.authenticate(headers["Authorization"][7:])
    with catalog.identity.db.transaction() as session:
        session.execute(
            delete(role_permissions).where(
                role_permissions.c.role_id == "CUSTOMER",
                role_permissions.c.permission_id == "product.read",
            )
        )
    try:
        with client(catalog) as http:
            assert http.get("/api/v1/products", headers=headers).status_code == 404
    finally:
        with catalog.identity.db.transaction() as session:
            session.execute(
                insert(role_permissions).values(role_id="CUSTOMER", permission_id="product.read")
            )
    with catalog.identity.db.transaction() as session:
        session.execute(
            update(sessions).where(sessions.c.id == principal.session_id).values(revoked=True)
        )
    with pytest.raises(IdentityError):
        catalog.search(principal)
    with client(catalog) as http:
        assert http.get("/api/v1/products", headers=headers).status_code == 401


def test_invalid_stored_specs_fail_closed(catalog):
    with catalog.identity.db.transaction() as session:
        session.execute(
            update(t.skus)
            .where(t.skus.c.tenant_id == catalog.test_tenant)
            .values(specifications={"bad": "shape"})
        )
    with client(catalog) as http:
        response = http.get("/api/v1/products/P1/specifications", headers=credentials(catalog))
        assert (
            response.status_code == 503
            and response.json()["error"]["code"] == "CATALOG_DATA_INVALID"
        )
        assert "bad" not in response.text


def test_forged_principal_and_inactive_membership(catalog):
    headers = credentials(catalog)
    principal = catalog.identity.authenticate(headers["Authorization"][7:])
    with pytest.raises(IdentityError):
        catalog.search(replace(principal, tenant_id=catalog.test_other, role="ADMIN"))
    with catalog.identity.db.transaction() as session:
        session.execute(
            update(memberships)
            .where(
                memberships.c.tenant_id == principal.tenant_id,
                memberships.c.user_id == principal.user_id,
            )
            .values(active=False)
        )
    with client(catalog) as http:
        assert http.get("/api/v1/products", headers=headers).status_code == 401


@pytest.mark.parametrize("status", ["DRAFT", "OFF_SHELF", "DISCONTINUED"])
def test_sku_visibility_also_applies_to_admin(catalog, status):
    with catalog.identity.db.transaction() as session:
        session.execute(
            update(t.skus).where(t.skus.c.tenant_id == catalog.test_tenant).values(status=status)
        )
    with client(catalog) as http:
        headers = credentials(catalog, "ADMIN")
        assert http.get("/api/v1/products/P1/skus/BLACK", headers=headers).status_code == 404
        assert (
            http.get("/api/v1/products/P1/specifications", headers=headers).json()["data"]["items"]
            == []
        )


def test_query_dependency_failure_is_sanitized(catalog, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def unavailable(*args, **kwargs):
        raise OperationalError("private-sql", {}, RuntimeError("private-driver"))

    headers = credentials(catalog)
    monkeypatch.setattr(catalog, "_read", unavailable)
    with client(catalog) as http:
        response = http.get("/api/v1/products/P1", headers=headers)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "CATALOG_UNAVAILABLE"
        assert "private" not in response.text


def test_catalog_openapi_requires_bearer(catalog):
    schema = create_app(identity=catalog.identity, catalog=catalog).openapi()
    routes = {
        path: value
        for path, value in schema["paths"].items()
        if path.startswith("/api/v1/products")
    }
    assert len(routes) == 5
    for operations in routes.values():
        assert set(operations) == {"get"}
        assert operations["get"]["security"] == [{"HTTPBearer": []}]
        assert "401" in operations["get"]["responses"]
