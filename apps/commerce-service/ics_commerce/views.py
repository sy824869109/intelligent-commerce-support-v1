"""商品查询响应合同；来源、时效和未知状态必须对调用者显式可见。"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Ref = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")]
Quantity = Annotated[int, Field(ge=0, le=9007199254740991)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Observation(Model):
    source: Ref
    source_version: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,18}$")]
    as_of: datetime
    synced_at: datetime
    freshness: Literal["FRESH", "STALE", "FUTURE"]


class Category(Model):
    id: Ref
    name: str
    parent_id: Ref | None
    observation: Observation


class Product(Model):
    id: Ref
    category_id: Ref
    name: str
    description: str
    status: Literal["ON_SALE"]
    observation: Observation


class ProductDetail(Product):
    category: Category | None


class ProductPage(Model):
    items: list[Product]
    next_cursor: Ref | None
    has_more: bool


class Attribute(Model):
    product_id: Ref
    name: str
    value: str
    unit: str | None
    observation: Observation


class Sku(Model):
    id: Ref
    product_id: Ref
    code: Ref
    specifications: list[tuple[str, str]]
    status: Literal["ON_SALE"]
    observation: Observation


class Specifications(Model):
    product_id: Ref
    attributes: list[Attribute]
    items: list[Sku]
    has_more: bool
    next_cursor: Ref | None


class Price(Model):
    sku_id: Ref
    minor_units: Quantity
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    valid_from: datetime
    valid_until: datetime | None
    observation: Observation


class Inventory(Model):
    sku_id: Ref
    available_quantity: Quantity | None
    observation: Observation


class SkuFacts(Model):
    sku: Sku
    price: Price | None
    price_state: Literal["UNKNOWN", "FUTURE", "STALE", "NOT_STARTED", "EXPIRED", "AVAILABLE"]
    inventory: Inventory | None
    inventory_state: Literal["UNKNOWN", "FUTURE", "STALE", "IN_STOCK", "OUT_OF_STOCK"]
    is_checkout_quote: Literal[False]
    stock_reserved: Literal[False]


class Activity(Model):
    product_id: Ref
    state: Literal["UNKNOWN"]
    source: None
    explanation: str
