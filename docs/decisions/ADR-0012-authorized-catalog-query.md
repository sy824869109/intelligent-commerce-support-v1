# ADR-0012：商品查询授权与事实观察边界

- 状态：Accepted
- 日期：2026-09-14
- 关联任务：M04.2

## 背景

M04.1 六张读模型表已经存在，M03 只有订单、工单和知识权限。现在需要真实 SQL 商品查询，而非内存示例；同步数据源尚未实现。

## 决策驱动因素

不串租户、不把未知当零、不用模型推测优惠；复用现有单进程部署和依赖，不新增环境。Gateway 只做协议与安全入口，Commerce 持有业务查询。

## 决策

1. 新增 `apps/commerce-service/ics_commerce`，运行时由 `run_gateway.py --with-database` 显式装配。没有另开 Commerce HTTP 进程。
2. 迁移 m04_0005 新增 product.read，以及 CUSTOMER/AGENT/ADMIN 三条授权。已发布迁移不修改。请求经 M03 验证 Bearer，Commerce 事务中再次读取有效会话、当前角色及权限。tenant_id 只取校验后的身份；每条 SQL 都带该租户。
3. 本组是客户只读查询，三角色均只能读取 ON_SALE 商品及 ON_SALE SKU；草稿/下架/停售/不存在统一 404，ADMIN 也不绕过。后台维护接口未来单独设计。
4. 搜索和 SKU 分页按 ID 升序，limit 为 1–100、默认 20，after 为排他 ID 下界；每次请求独立校验权限和筛选。不保证跨页一致性快照；改筛选应重置游标。名称使用参数化字面包含匹配，转义 SQL LIKE 元字符，不是语义搜索。类目只筛精确 ID，不递归。
5. 数据先经过 M04.1 模型验证再投影；SQL UTC 转带时区 UTC。source_version 输出字符串，避免 JavaScript 超大整数精度丢失；金额仍为安全范围整数最小单位。规格 JSON 使用二元数组列表，不接受任意对象。
6. 每个事实独立返回来源与 freshness。当前保守窗口 300 秒，age >= 300 为 STALE，来源晚于当前时刻为 FUTURE；synced_at 不刷新旧事实时效。窗口是查询策略，不是上游实时 SLA；分来源配置后续通过 ADR 扩展。
7. 价格报告 UNKNOWN/FUTURE/STALE/NOT_STARTED/EXPIRED/AVAILABLE；库存报告 UNKNOWN/FUTURE/STALE/IN_STOCK/OUT_OF_STOCK。旧快照仍可显示，但不能当当前报价或供货承诺。库存缺行与 NULL 都为 UNKNOWN，原始 snapshot 是否存在仍可区分；NULL 快照的时效见 observation。
8. 现阶段无活动事实或发布知识来源。activity 端点只返回经过商品鉴权的 UNKNOWN 与说明，不能说“没有活动”，不能计算优惠或承诺叠加。M09/M10 接入版本化来源后扩展合同；本步不伪造活动系统。
9. 沿用 no-store、request_id、trace_id 和脱敏日志。SQL/脏数据错误返回稳定 503；认证层数据库故障仍遵循现有通用 500 边界，不泄漏 SQL/凭据。读取不生成 Outbox 或伪造写审计。

## 备选方案

Gateway 内写 SQL 会破坏所有权；复用 knowledge.read 会混淆资源；向量检索代替价格库存 SQL 会弱化事实可靠性，均不采用。当前不引入额外全文检索服务。

## 结果与影响

交付五个 HTTP 入口和可复用 Commerce 方法；商品与 SKU 分页，属性最多 100 条，超过显式失败。使用现有 READ COMMITTED 短事务，各表快照可能来自不同时间，不承诺组合原子报价；is_checkout_quote/stock_reserved 恒为 false。

## 安全与数据影响

迁移只有权限种子，不新增商品表、不写商品。业务模块不是独立 DB 安全沙箱，授权由服务端代码强制。名称/描述/规格是纯文本，不是可信 HTML 或模型指令；前端转义和后续 RAG 注入防护仍须实施。V1 尚未发布局域网。

## 运维与回滚

显式升级并核验开发库，启动不自动迁移。m04_0005 在撤权限前检查业务非空，禁止盲目降级。生产回退应停用新端点并制定向前修复迁移；不能直接回退到要求旧 HEAD 的程序。

## 验证方式

同一组 HTTP/SQL 用例运行在 SQLite 和临时真实 MySQL：三角色、登录、跨租户、隐藏商品、错误父子关系、参数污染、字面搜索、未知/零库存、来源过期/未来、价格时间窗、吊销及脏规格。旧库 m03→m04_0004→m04_0005 保留数据。OpenAPI 独立生成与漂移校验，不覆盖 M02/M03 冻结文件。
