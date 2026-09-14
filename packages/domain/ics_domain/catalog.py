"""M04.1 商品读快照；不是写库服务、支付报价或库存预留能力。"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
import re

MAX_SAFE_INTEGER = 9007199254740991


def identifier(value: str) -> None:
    """标识不接受空白和隐式类型转换，避免跨系统产生不同的资源键。"""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", value):
        raise ValueError("Invalid catalog identifier")


def label(value: str, limit: int) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("Invalid catalog label")


def integer(value: int, minimum: int = 0, maximum: int = MAX_SAFE_INTEGER) -> None:
    # bool 是 int 的子类，但库存 True 和金额 True 不能当成 1。
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid catalog integer")


def utc(value: datetime) -> None:
    """领域边界要求带时区 UTC；Commerce SQL 读取适配显式转换数据库时间。"""
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError("Catalog timestamps require aware UTC")


class SaleStatus(StrEnum):
    DRAFT = "DRAFT"
    ON_SALE = "ON_SALE"
    OFF_SHELF = "OFF_SHELF"
    DISCONTINUED = "DISCONTINUED"


@dataclass(frozen=True, kw_only=True)
class Observation:
    """来源版本只能在同一来源内比较；同步时间不替代来源时间。"""

    source: str
    source_version: int
    as_of: datetime
    synced_at: datetime

    def __post_init__(self):
        identifier(self.source)
        integer(self.source_version, 1, 9223372036854775807)
        utc(self.as_of)
        utc(self.synced_at)
        if self.as_of > self.synced_at:
            raise ValueError("Source timestamp is ahead of receipt")


@dataclass(frozen=True, kw_only=True)
class ScopedSnapshot:
    """只标记数据归属，不代表调用者已经得到这个租户的授权。"""

    tenant_id: str
    observation: Observation

    def __post_init__(self):
        identifier(self.tenant_id)
        if not isinstance(self.observation, Observation):
            raise ValueError("A validated observation is required")


@dataclass(frozen=True, kw_only=True)
class Category(ScopedSnapshot):
    id: str
    name: str
    parent_id: str | None = None

    def __post_init__(self):
        super().__post_init__()
        identifier(self.id)
        label(self.name, 120)
        if self.parent_id is not None:
            identifier(self.parent_id)
            if self.parent_id == self.id:
                raise ValueError("Category cannot be its own parent")


@dataclass(frozen=True, kw_only=True)
class Product(ScopedSnapshot):
    id: str
    category_id: str
    name: str
    description: str
    status: SaleStatus

    def __post_init__(self):
        super().__post_init__()
        identifier(self.id)
        identifier(self.category_id)
        label(self.name, 200)
        if (
            not isinstance(self.description, str)
            or len(self.description) > 10000
            or "\x00" in self.description
        ):
            raise ValueError("Invalid product description")
        if not isinstance(self.status, SaleStatus):
            raise ValueError("Explicit product sale status required")


@dataclass(frozen=True, kw_only=True)
class ProductAttribute(ScopedSnapshot):
    product_id: str
    name: str
    value: str
    unit: str | None = None

    def __post_init__(self):
        super().__post_init__()
        identifier(self.product_id)
        label(self.name, 64)
        label(self.value, 2000)
        if self.unit is not None:
            label(self.unit, 32)


@dataclass(frozen=True, kw_only=True)
class Sku(ScopedSnapshot):
    id: str
    product_id: str
    code: str
    specifications: tuple[tuple[str, str], ...]
    status: SaleStatus

    def __post_init__(self):
        super().__post_init__()
        for value in (self.id, self.product_id, self.code):
            identifier(value)
        if not isinstance(self.status, SaleStatus):
            raise ValueError("Explicit SKU sale status required")
        # 不保留调用者可修改的 dict/list；无规格商品允许空元组。
        if type(self.specifications) is not tuple or len(self.specifications) > 32:
            raise ValueError("Specifications require a bounded immutable tuple")
        names = set()
        for pair in self.specifications:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError("Invalid specification pair")
            key, value = pair
            label(key, 64)
            label(value, 200)
            if key != key.strip() or key in names:
                raise ValueError("Duplicate or ambiguous specification name")
            names.add(key)


@dataclass(frozen=True, kw_only=True)
class SkuPrice(ScopedSnapshot):
    """币种最小单位整数，与既有 Money 合同一致；不是最终支付金额。"""

    sku_id: str
    minor_units: int
    currency: str
    valid_from: datetime
    valid_until: datetime | None = None

    def __post_init__(self):
        super().__post_init__()
        identifier(self.sku_id)
        integer(self.minor_units)
        if not isinstance(self.currency, str) or not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("Invalid currency code")
        utc(self.valid_from)
        if self.valid_until is not None:
            utc(self.valid_until)
            if self.valid_until <= self.valid_from:
                raise ValueError("Price validity uses a non-empty half-open interval")


@dataclass(frozen=True, kw_only=True)
class SkuInventory(ScopedSnapshot):
    """上游可售量只读快照；None 是未知，0 是缺货，不参与扣减或预留。"""

    sku_id: str
    available_quantity: int | None

    def __post_init__(self):
        super().__post_init__()
        identifier(self.sku_id)
        if self.available_quantity is not None:
            integer(self.available_quantity)
