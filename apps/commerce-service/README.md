# commerce-service

电商领域事实服务。

- 负责：商品、SKU、库存读模型、订单、支付摘要、物流、售后和发票。
- 拥有数据：对应电商领域表及其 Outbox 事件。
- 禁止：让 LLM 直接执行 SQL 或写入退款、支付、库存等状态。
- 当前实现：M04.1 六类商品读模型、M04.2 授权商品查询；订单、物流和售后按后续任务逐步补齐。

## 本步职责与代码

纯模型在 `packages/domain/ics_domain/catalog.py`；SQL 映射在 `packages/persistence/ics_persistence/commerce_schema.py`。`ics_commerce/catalog.py` 负责权限、查询和时效，`views.py` 定义对外响应。V1 由 Gateway 同进程装配，不另开服务；复用现有依赖。

查询输入是已鉴别的 Principal 会话引用、资源编号与受限参数；事务内重查权限，租户不取客户端参数。输出是本租户上架商品及各自来源；UNKNOWN 不补零。内部非法数据转稳定 503，不泄漏 SQL。401 无身份、404 不可见、422 参数无效；认证层依赖故障沿用 Gateway 通用 500。

拥有表：`commerce_categories`、`commerce_products`、`commerce_product_attributes`、`commerce_skus`、`commerce_sku_prices`、`commerce_sku_inventory`。表由 m04_0004 创建；当前头 m04_0005 只补 product.read 权限。缺失价格不是免费；NULL 库存不是 0；来源时间不是同步时间。

## 本机学习与验证

在项目根目录先执行 `. .\scripts\enter_environment.ps1`：

```powershell
python scripts/demo_catalog_models.py
python scripts/check_backend.py tests
python scripts/check_mysql.py
python scripts/check_catalog_local.py
python scripts/run_gateway.py --with-database
```

示例仅在内存构造“黑色库存 12、白色库存未知”的耳机，不写数据库。MySQL 测试只在工具独有临时容器运行，结束清理合成 tmpfs 数据。实际开发库由 `python scripts/check_catalog_local.py --upgrade` 显式迁移，不提供无保护的降级入口。

详见 [M04.1](../../docs/operations/m04-1-catalog-models.md)、[M04.2 教程](../../docs/operations/m04-2-authorized-catalog.md)、[OpenAPI](../../docs/api/m04-catalog.openapi.json)、[ADR-0012](../../docs/decisions/ADR-0012-authorized-catalog-query.md)。同步幂等属于 M04.3；活动来源在 M09/M10 接入，目前明确 UNKNOWN，不计算优惠。
