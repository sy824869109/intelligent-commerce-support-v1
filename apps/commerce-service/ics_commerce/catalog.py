"""授权商品只读端口：先核验作用域，再读取事实，永不调用模型补齐数据。"""

from dataclasses import asdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ics_domain import catalog as domain
from ics_identity.service import IdentityError, Resource
from ics_persistence import commerce_schema as tables


class CatalogError(Exception):
    def __init__(self, code, status=503):
        self.code, self.status = code, status
        super().__init__(code)


def snapshot(model, row):
    """SQL 无时区 UTC 转成领域 UTC；数据库脏数据不得直接成为对外事实。"""
    values = dict(row)
    observation = {}
    for key in ("source", "source_version", "as_of", "synced_at"):
        observation[key] = values.pop(key)
    for key in ("as_of", "synced_at"):
        observation[key] = observation[key].replace(tzinfo=timezone.utc)
    values["observation"] = domain.Observation(**observation)
    if "status" in values:
        values["status"] = domain.SaleStatus(values["status"])
    if "specifications" in values:
        pairs = values["specifications"]
        if not isinstance(pairs, list) or any(not isinstance(pair, list) for pair in pairs):
            raise ValueError("Specifications must be a JSON array of pairs")
        values["specifications"] = tuple(tuple(pair) for pair in pairs)
    for key in ("valid_from", "valid_until"):
        if values.get(key) is not None:
            values[key] = values[key].replace(tzinfo=timezone.utc)
    return model(**values)


def public(model, current):
    value = asdict(model)
    value.pop("tenant_id")
    # 版本可超过 JavaScript 安全整数；对外用十进制字符串避免前端舍入。
    value["observation"]["source_version"] = str(model.observation.source_version)
    age = current - model.observation.as_of
    value["observation"]["freshness"] = (
        "FUTURE" if age < timedelta(0) else "STALE" if age >= timedelta(minutes=5) else "FRESH"
    )
    return value


class Catalog:
    """所有公开方法都重新授权；principal 仅作会话引用，不信任其角色声明。"""

    def __init__(self, identity, clock=None):
        self.identity = identity
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _scope(self, session, principal):
        return self.identity.authorize(
            session,
            principal,
            "product.read",
            Resource("product", principal.tenant_id, published=True, customer_visible=True),
        ).tenant_id

    @contextmanager
    def transaction(self):
        """依赖故障返回稳定错误码，不泄漏驱动 SQL、参数或连接配置。"""
        try:
            with self.identity.db.transaction() as session:
                yield session
        except SQLAlchemyError:
            raise CatalogError("CATALOG_UNAVAILABLE") from None

    def _read(self, session, table, model, current, **keys):
        row = session.execute(select(table).filter_by(**keys)).mappings().first()
        if row is None:
            return None
        try:
            return public(snapshot(model, row), current)
        except (ValueError, TypeError, AttributeError):
            raise CatalogError("CATALOG_DATA_INVALID") from None

    def _product(self, session, tenant, product_id, current):
        item = self._read(
            session,
            tables.products,
            domain.Product,
            current,
            tenant_id=tenant,
            id=product_id,
            status="ON_SALE",
        )
        # 客户接口对三种角色采用同一可见性，不让管理员路径泄漏草稿给聊天。
        if item is None:
            raise IdentityError("ACCESS_DENIED", 404)
        return item

    def search(self, principal, *, q="", category_id=None, after=None, limit=20):
        """确定顺序的 ID 游标；参数化字面包含搜索，不把 %/_ 当通配符。"""
        if not isinstance(q, str) or len(q) > 100 or any(ord(c) < 32 for c in q):
            raise CatalogError("INPUT_INVALID", 422)
        try:
            domain.integer(limit, 1, 100)
            for key in (category_id, after):
                if key is not None:
                    domain.identifier(key)
        except ValueError:
            raise CatalogError("INPUT_INVALID", 422) from None
        with self.transaction() as session:
            tenant = self._scope(session, principal)
            query = select(tables.products).where(
                tables.products.c.tenant_id == tenant, tables.products.c.status == "ON_SALE"
            )
            if q.strip():
                query = query.where(tables.products.c.name.contains(q.strip(), autoescape=True))
            if category_id is not None:
                query = query.where(tables.products.c.category_id == category_id)
            if after is not None:
                query = query.where(tables.products.c.id > after)
            rows = (
                session.execute(query.order_by(tables.products.c.id).limit(limit + 1))
                .mappings()
                .all()
            )
            current = self.clock()
            try:
                items = [public(snapshot(domain.Product, row), current) for row in rows[:limit]]
            except (ValueError, TypeError, AttributeError):
                raise CatalogError("CATALOG_DATA_INVALID") from None
            return {
                "items": items,
                "next_cursor": items[-1]["id"] if len(rows) > limit else None,
                "has_more": len(rows) > limit,
            }

    def detail(self, principal, product_id):
        """读取本租户已上架商品及类目；不存在与不可见统一拒绝。"""
        with self.transaction() as session:
            tenant = self._scope(session, principal)
            current = self.clock()
            item = self._product(session, tenant, product_id, current)
            item["category"] = self._read(
                session,
                tables.categories,
                domain.Category,
                current,
                tenant_id=tenant,
                id=item["category_id"],
            )
            return item

    def specifications(self, principal, product_id, *, after=None, limit=20):
        """分页读取上架 SKU 与最多百条属性，不静默截断不完整的属性集。"""
        with self.transaction() as session:
            tenant = self._scope(session, principal)
            current = self.clock()
            self._product(session, tenant, product_id, current)
            query = select(tables.skus).where(
                tables.skus.c.tenant_id == tenant,
                tables.skus.c.product_id == product_id,
                tables.skus.c.status == "ON_SALE",
            )
            if after is not None:
                domain.identifier(after)
                query = query.where(tables.skus.c.id > after)
            domain.integer(limit, 1, 100)
            rows = (
                session.execute(query.order_by(tables.skus.c.id).limit(limit + 1)).mappings().all()
            )
            attrs = (
                session.execute(
                    select(tables.attributes)
                    .where(
                        tables.attributes.c.tenant_id == tenant,
                        tables.attributes.c.product_id == product_id,
                    )
                    .order_by(tables.attributes.c.name)
                    .limit(101)
                )
                .mappings()
                .all()
            )
            if len(attrs) > 100:
                raise CatalogError("CATALOG_DATA_INVALID")
            try:
                items = [public(snapshot(domain.Sku, row), current) for row in rows[:limit]]
                attributes = [
                    public(snapshot(domain.ProductAttribute, row), current) for row in attrs
                ]
            except (ValueError, TypeError, AttributeError):
                raise CatalogError("CATALOG_DATA_INVALID") from None
            return {
                "product_id": product_id,
                "attributes": attributes,
                "items": items,
                "has_more": len(rows) > limit,
                "next_cursor": items[-1]["id"] if len(rows) > limit else None,
            }

    def sku(self, principal, product_id, sku_id):
        """校验 SKU 属于该商品，再返回独立的价格与库存观察状态。"""
        with self.transaction() as session:
            tenant = self._scope(session, principal)
            current = self.clock()
            self._product(session, tenant, product_id, current)
            sku = self._read(
                session,
                tables.skus,
                domain.Sku,
                current,
                tenant_id=tenant,
                id=sku_id,
                product_id=product_id,
                status="ON_SALE",
            )
            if sku is None:
                raise IdentityError("ACCESS_DENIED", 404)
            price = self._read(
                session, tables.prices, domain.SkuPrice, current, tenant_id=tenant, sku_id=sku_id
            )
            stock = self._read(
                session,
                tables.inventory,
                domain.SkuInventory,
                current,
                tenant_id=tenant,
                sku_id=sku_id,
            )
            price_state = "UNKNOWN"
            if price:
                price_state = price["observation"]["freshness"]
                if price_state == "FRESH":
                    price_state = (
                        "NOT_STARTED"
                        if current < price["valid_from"]
                        else (
                            "EXPIRED"
                            if price["valid_until"] and current >= price["valid_until"]
                            else "AVAILABLE"
                        )
                    )
            stock_state = "UNKNOWN"
            if stock and stock["available_quantity"] is not None:
                stock_state = stock["observation"]["freshness"]
                if stock_state == "FRESH":
                    stock_state = "IN_STOCK" if stock["available_quantity"] > 0 else "OUT_OF_STOCK"
            return {
                "sku": sku,
                "price": price,
                "price_state": price_state,
                "inventory": stock,
                "inventory_state": stock_state,
                "is_checkout_quote": False,
                "stock_reserved": False,
            }

    def activity(self, principal, product_id):
        """鉴权后的活动可用性说明；未接活动来源时不虚构优惠事实。"""
        self.detail(principal, product_id)
        # M09/M10 尚未交付活动知识来源，禁止把缺失来源等同“没有优惠”。
        return {
            "product_id": product_id,
            "state": "UNKNOWN",
            "source": None,
            "explanation": "暂无可核实的活动信息，不能确认优惠或叠加规则。",
        }
