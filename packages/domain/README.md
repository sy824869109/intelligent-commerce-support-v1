# domain

保存与 Web 框架、数据库和模型厂商无关的领域值对象、规则和状态机。这里不允许依赖 FastAPI、SQLAlchemy、LangChain 或具体客户端。

M04.1 的 `ics_domain.catalog` 提供 Category、Product、ProductAttribute、Sku、SkuPrice、SkuInventory 以及来源 Observation。均为冻结 dataclass，拒绝隐式金额/库存类型转换。tenant_id 表达归属而非授权；纯对象不会读写数据库。

运行教学示例：项目根目录 `python scripts/demo_catalog_models.py`。模型测试已纳入 `python scripts/check_backend.py tests`，使用已有 V1 解释器。
