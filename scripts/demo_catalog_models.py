"""M04.1 纯模型教学示例：合成数据，不连接数据库、不调用模型、不写商品。"""

from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/domain"))

from ics_domain.catalog import Observation, Product, SaleStatus, Sku, SkuInventory, SkuPrice


def main():
    """显示同一商品两个规格的不同库存，示范未知值不能变成缺货。"""
    now = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
    stamp = Observation(source="synthetic-erp", source_version=1, as_of=now, synced_at=now)
    scope = dict(tenant_id="SHOP_A", observation=stamp)
    product = Product(
        **scope,
        id="P1",
        category_id="C1",
        name="蓝牙耳机",
        description="合成演示，不是实际在售商品",
        status=SaleStatus.ON_SALE,
    )
    print("M04.1 合成模型示例：不连接任何服务、不写库")
    print(f"店铺={product.tenant_id} 商品={product.id} 名称={product.name}")
    for code, color, quantity in (("BLACK", "黑色", 12), ("WHITE", "白色", None)):
        sku = Sku(
            **scope,
            id=code,
            product_id=product.id,
            code=code,
            specifications=(("颜色", color),),
            status=SaleStatus.ON_SALE,
        )
        price = SkuPrice(**scope, sku_id=sku.id, minor_units=29900, currency="CNY", valid_from=now)
        stock = SkuInventory(**scope, sku_id=sku.id, available_quantity=quantity)
        stock_text = (
            "未知，不能回答缺货"
            if stock.available_quantity is None
            else str(stock.available_quantity)
        )
        print(
            f"SKU={sku.id} 颜色={color} 价格={price.minor_units // 100}.{price.minor_units % 100:02d} CNY 库存={stock_text}"
        )
    print("当前只是读模型；查询鉴权接口在 M04.2，同步与幂等任务在 M04.3。")


if __name__ == "__main__":
    main()
