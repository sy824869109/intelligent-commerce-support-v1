"""商品纯模型校验；数据库约束另在真实 MySQL 中验收。"""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from ics_domain.catalog import (
    Category,
    Observation,
    Product,
    ProductAttribute,
    SaleStatus,
    Sku,
    SkuInventory,
    SkuPrice,
)

NOW = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
STAMP = Observation(source="erp", source_version=1, as_of=NOW, synced_at=NOW)
SCOPE = dict(tenant_id="SHOP_A", observation=STAMP)


def test_six_models_describe_one_product_without_network_or_database():
    category = Category(**SCOPE, id="C1", name="耳机")
    product = Product(
        **SCOPE,
        id="P1",
        category_id=category.id,
        name="蓝牙耳机",
        description="主动降噪",
        status=SaleStatus.ON_SALE,
    )
    attribute = ProductAttribute(
        **SCOPE, product_id=product.id, name="续航", value="30", unit="小时"
    )
    sku = Sku(
        **SCOPE,
        id="S1",
        product_id=product.id,
        code="HEADPHONE-BLACK",
        specifications=(("颜色", "黑色"),),
        status=SaleStatus.ON_SALE,
    )
    price = SkuPrice(**SCOPE, sku_id=sku.id, minor_units=29900, currency="CNY", valid_from=NOW)
    stock = SkuInventory(**SCOPE, sku_id=sku.id, available_quantity=12)
    assert attribute.unit == "小时" and price.minor_units == 29900
    assert stock.available_quantity == 12 and sku.specifications == (("颜色", "黑色"),)
    with pytest.raises(FrozenInstanceError):
        price.minor_units = 1


@pytest.mark.parametrize("quantity", [None, 0, 12])
def test_inventory_unknown_zero_and_positive_are_distinct(quantity):
    stock = SkuInventory(**SCOPE, sku_id="S1", available_quantity=quantity)
    assert stock.available_quantity is quantity


@pytest.mark.parametrize("amount", [0, 9007199254740991])
def test_price_extremes_match_existing_public_money_contract(amount):
    from ics_contracts.commerce import Money

    price = SkuPrice(**SCOPE, sku_id="S1", minor_units=amount, currency="CNY", valid_from=NOW)
    assert Money(minor_units=price.minor_units, currency=price.currency).minor_units == amount


@pytest.mark.parametrize("amount", [-1, True, 29.9, "2990", 9007199254740992])
def test_price_and_inventory_reject_implicit_or_unsafe_numbers(amount):
    with pytest.raises(ValueError):
        SkuPrice(**SCOPE, sku_id="S1", minor_units=amount, currency="CNY", valid_from=NOW)
    with pytest.raises(ValueError):
        SkuInventory(**SCOPE, sku_id="S1", available_quantity=amount)


@pytest.mark.parametrize("currency", ["cny", "CN", "CNYX", "123", None])
def test_currency_shape_is_explicit(currency):
    with pytest.raises(ValueError):
        SkuPrice(**SCOPE, sku_id="S1", minor_units=0, currency=currency, valid_from=NOW)


@pytest.mark.parametrize(
    "change",
    [
        {"source_version": 0},
        {"source_version": True},
        {"source": "bad source"},
        {"as_of": NOW.replace(tzinfo=None)},
        {"synced_at": NOW - timedelta(seconds=1)},
        {"as_of": NOW.astimezone(timezone(timedelta(hours=8)))},
    ],
)
def test_observation_rejects_ambiguous_source_time_and_version(change):
    with pytest.raises(ValueError):
        replace(STAMP, **change)


def test_resync_does_not_advance_source_timestamp():
    newer_receipt = replace(STAMP, synced_at=NOW + timedelta(minutes=10))
    assert newer_receipt.as_of == STAMP.as_of


@pytest.mark.parametrize("end", [NOW, NOW - timedelta(seconds=1), NOW.replace(tzinfo=None)])
def test_price_window_is_nonempty_and_utc(end):
    with pytest.raises(ValueError):
        SkuPrice(
            **SCOPE, sku_id="S1", minor_units=1, currency="CNY", valid_from=NOW, valid_until=end
        )


@pytest.mark.parametrize(
    "specs",
    [
        {"颜色": "黑"},
        [("颜色", "黑")],
        (("颜色", "黑"), ("颜色", "白")),
        ((" 颜色", "黑"),),
        (("颜色", ""),),
        (("颜色",),),
        tuple((str(i), "x") for i in range(33)),
    ],
)
def test_sku_rejects_mutable_duplicate_and_ambiguous_specifications(specs):
    with pytest.raises(ValueError):
        Sku(
            **SCOPE,
            id="S1",
            product_id="P1",
            code="BLACK",
            specifications=specs,
            status=SaleStatus.ON_SALE,
        )


def test_category_self_reference_and_snapshot_scope_require_validation():
    with pytest.raises(ValueError):
        Category(**SCOPE, id="C1", parent_id="C1", name="耳机")
    with pytest.raises(ValueError):
        Category(tenant_id=" ", observation=STAMP, id="C1", name="耳机")
    with pytest.raises(ValueError):
        Category(tenant_id="A", observation={}, id="C1", name="耳机")


def test_product_status_and_attribute_labels_are_not_silently_coerced():
    with pytest.raises(ValueError):
        Product(**SCOPE, id="P1", category_id="C1", name="耳机", description="", status="ON_SALE")
    with pytest.raises(ValueError):
        ProductAttribute(**SCOPE, product_id="P1", name="续航", value="30", unit="\x00")
