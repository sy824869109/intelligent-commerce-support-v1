# commerce-service

电商领域事实服务。

- 负责：商品、SKU、库存读模型、订单、支付摘要、物流、售后和发票。
- 拥有数据：对应电商领域表及其 Outbox 事件。
- 禁止：让 LLM 直接执行 SQL 或写入退款、支付、库存等状态。
- 当前实现：M04.1 六类商品读模型；订单、物流和售后按后续任务逐步补齐。

## 本步职责与代码

纯模型在 `packages/domain/ics_domain/catalog.py`；数据库映射在 `packages/persistence/ics_persistence/commerce_schema.py`。这是逻辑服务的数据模型阶段，没有启动新的 HTTP 服务进程。使用已有 V1 Python 和 SQLAlchemy/Alembic，不新增依赖。

输入是明确的租户、资源编号、商品/SKU 状态、规格、金额、库存及来源快照；输出为不可变值对象。非法类型、负数、非法时间或重复规格名抛出 `ValueError`，这是内部模型异常，不是已经发布的 HTTP 错误协议。M04.2 再将模型映射为接口合同。

拥有表：`commerce_categories`、`commerce_products`、`commerce_product_attributes`、`commerce_skus`、`commerce_sku_prices`、`commerce_sku_inventory`。迁移头 `m04_0004`，只添加空表。缺失价格不是免费；库存 NULL 不是 0；source 时间不是 synced_at 时间。

## 本机学习与验证

在项目根目录先执行 `. .\scripts\enter_environment.ps1`：

```powershell
python scripts/demo_catalog_models.py
python scripts/check_backend.py tests
python scripts/check_mysql.py
python scripts/check_catalog_local.py
```

示例仅在内存构造“黑色库存 12、白色库存未知”的耳机，不写数据库。MySQL 测试只在工具独有临时容器运行，结束清理合成 tmpfs 数据。实际开发库由 `python scripts/check_catalog_local.py --upgrade` 显式迁移，不提供无保护的降级入口。

详见 [M04.1 教学与实施记录](../../docs/operations/m04-1-catalog-models.md) 和 [ADR-0011](../../docs/decisions/ADR-0011-catalog-read-models.md)。查询权限、搜索、详情与库存接口属于 M04.2，同步幂等属于 M04.3，本步没有绕过 M03 新增公开读取入口。
