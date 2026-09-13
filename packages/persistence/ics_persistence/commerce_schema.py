"""M04.1 商品读模型的物理映射；数据所有权归 Commerce，不包含授权或同步规则。"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME

from .identity_schema import metadata, OPTIONS

# MySQL 默认 DATETIME 会丢弃微秒，来源时间和价格窗口显式保留六位精度。
TIMESTAMP = DateTime().with_variant(DATETIME(fsp=6), "mysql")


def scope():
    """复合主键让同一外部 ID 可以存在于不同租户，关联必须同时携带租户。"""
    return [
        Column("tenant_id", String(64), primary_key=True),
        Column("id", String(64), primary_key=True),
    ]


def observation(prefix):
    """来源时间和同步时间分开；重新同步旧快照不能让旧数据看起来更新。"""
    return [
        Column("source", String(64), nullable=False),
        Column("source_version", BigInteger, nullable=False),
        Column("as_of", TIMESTAMP, nullable=False),
        Column("synced_at", TIMESTAMP, nullable=False),
        CheckConstraint("source_version > 0", name=f"ck_{prefix}_version"),
        CheckConstraint("as_of <= synced_at", name=f"ck_{prefix}_time"),
    ]


categories = Table(
    "commerce_categories",
    metadata,
    *scope(),
    Column("name", String(120), nullable=False),
    Column("parent_id", String(64)),
    *observation("category"),
    ForeignKeyConstraint(["tenant_id"], ["identity_tenants.id"]),
    ForeignKeyConstraint(
        ["tenant_id", "parent_id"], ["commerce_categories.tenant_id", "commerce_categories.id"]
    ),
    CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_category_self"),
    **OPTIONS,
)
products = Table(
    "commerce_products",
    metadata,
    *scope(),
    Column("category_id", String(64), nullable=False),
    Column("name", String(200), nullable=False),
    Column("description", Text, nullable=False),
    Column("status", String(16), nullable=False),
    *observation("product"),
    ForeignKeyConstraint(
        ["tenant_id", "category_id"], ["commerce_categories.tenant_id", "commerce_categories.id"]
    ),
    CheckConstraint(
        "status IN ('DRAFT','ON_SALE','OFF_SHELF','DISCONTINUED')", name="ck_product_status"
    ),
    Index("ix_product_category", "tenant_id", "category_id", "status"),
    **OPTIONS,
)
attributes = Table(
    "commerce_product_attributes",
    metadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("product_id", String(64), primary_key=True),
    Column("name", String(64), primary_key=True),
    Column("value", String(2000), nullable=False),
    Column("unit", String(32)),
    *observation("attribute"),
    ForeignKeyConstraint(
        ["tenant_id", "product_id"], ["commerce_products.tenant_id", "commerce_products.id"]
    ),
    **OPTIONS,
)
skus = Table(
    "commerce_skus",
    metadata,
    *scope(),
    Column("product_id", String(64), nullable=False),
    Column("code", String(64), nullable=False),
    Column("specifications", JSON, nullable=False),
    Column("status", String(16), nullable=False),
    *observation("sku"),
    ForeignKeyConstraint(
        ["tenant_id", "product_id"], ["commerce_products.tenant_id", "commerce_products.id"]
    ),
    UniqueConstraint("tenant_id", "code", name="uq_sku_tenant_code"),
    CheckConstraint(
        "status IN ('DRAFT','ON_SALE','OFF_SHELF','DISCONTINUED')", name="ck_sku_status"
    ),
    Index("ix_sku_product", "tenant_id", "product_id"),
    **OPTIONS,
)
prices = Table(
    "commerce_sku_prices",
    metadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("sku_id", String(64), primary_key=True),
    Column("minor_units", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("valid_from", TIMESTAMP, nullable=False),
    Column("valid_until", TIMESTAMP),
    *observation("price"),
    ForeignKeyConstraint(["tenant_id", "sku_id"], ["commerce_skus.tenant_id", "commerce_skus.id"]),
    CheckConstraint("minor_units >= 0 AND minor_units <= 9007199254740991", name="ck_price_amount"),
    CheckConstraint(
        "length(currency) = 3 AND "
        "substr(currency,1,1) BETWEEN 'A' AND 'Z' AND "
        "substr(currency,2,1) BETWEEN 'A' AND 'Z' AND "
        "substr(currency,3,1) BETWEEN 'A' AND 'Z'",
        name="ck_price_currency",
    ),
    CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="ck_price_window"),
    **OPTIONS,
)
inventory = Table(
    "commerce_sku_inventory",
    metadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("sku_id", String(64), primary_key=True),
    # NULL 表示上游库存未知；0 才是明确缺货。不设置默认值。
    Column("available_quantity", BigInteger),
    *observation("inventory"),
    ForeignKeyConstraint(["tenant_id", "sku_id"], ["commerce_skus.tenant_id", "commerce_skus.id"]),
    CheckConstraint(
        "available_quantity IS NULL OR "
        "(available_quantity >= 0 AND available_quantity <= 9007199254740991)",
        name="ck_inventory_quantity",
    ),
    **OPTIONS,
)
TABLES = (categories, products, attributes, skus, prices, inventory)
