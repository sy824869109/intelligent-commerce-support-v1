# ADR-0007：SQL 短事务与事件账本基础

- 状态：Accepted
- 日期：2026-09-09
- 决策者：项目团队（用户授权继续 M02.2）
- 关联任务：M02.2
- 取代：无
- 被取代：无

## 背景

M01 已提供独立 MySQL，M02.1 尚未连接数据库。需要可复用的 SQL 基础而不能把订单、会话和 KF 数据归入 Gateway。

## 决策驱动因素

- 遵守领域所有权、E-06 同事务事件与至少一次投递语义。
- 原项目/KF 保持只读，已有 Docker 数据不迁移；新依赖和日志在项目内。
- 真实 MySQL 验证与跨平台快速测试分开，禁止 SQLite 替代并发数据库验收。

## 决策

新增 `packages/persistence/ics_persistence`，仅承载数据库基础设施，不依赖 apps，不放入纯领域包。
SQLAlchemy 2.0.52、Alembic 1.19.2、PyMySQL 1.2.0，沿用同步驱动，由有界线程执行网关健康探针。
连接池最多 5 个连接、无溢出；READ COMMITTED、UTC、连接/读/写 2 秒、锁等待 2 秒。
每个调用创建独立 Session，显式短事务；不在数据库事务内访问队列、模型或其他服务。

建立 `platform_outbox`、`platform_inbox`、独立 `platform_alembic_version`。
这是当前单库开发部署的基础事件账本，不是由网关拥有的业务表。生产者操作限定 producer/tenant；消费者限定 consumer/tenant/event，并验证来源类型/schema。
身份可信性仍由 M03 及领域入口提供，字段过滤不等于完整授权。
各领域后续接入时必须把自己的写入、审计和 Outbox 放到同一事务；未来物理拆库采用各所有者独立迁移和账本，不支持跨库原子事务。

事件以 UTC 秒精度保存，ID 不透明且区分大小写，payload 最大 16 KiB，优先保存引用。
认领使用 MySQL SKIP LOCKED、数据库时钟、有界租约和令牌栅栏；失败退避，耗尽进入持久 DEAD 状态，不删除历史。
ACK 只代表传输层持久受理；本次不接 Redis Relay、不实现业务处理器、不承诺聚合严格顺序或 exactly-once。

## 备选方案

### 方案 A

采用当前同步 SQLAlchemy/PyMySQL：事务与运维简单，局域网初期适用；需要控制线程和连接数量，本次采用。

### 方案 B

全异步驱动：高并发可能获益，但此时缺少负载证据，增加取消/迁移兼容复杂度；后续依据性能测试另行 ADR。

## 结果与影响

### 正面影响

事务、迁移、失败恢复可独立验证；Gateway 仍没有业务写端点。共享包不反向依赖应用。

### 负面影响与成本

同步调用不可被 HTTP 取消直接中止，因此真实探针限制同一实例最多一个在途 DB 调用，驱动超时兜底。
事件身份/租户检查不是数据库行级授权；完整权限与处理器隔离尚待后续。

## 安全与数据影响

本机加载器只读取新平台非 root MySQL 凭据，并校验 Compose 所有权、容器镜像、端口与 schema/user。
本阶段限回环、合成数据，不提供生产 TLS 或局域网入口。SQL 参数不回显，失败不输出原始驱动异常。
迁移只建三张新表，不修改 M01 探针表、其他数据库或 KF。

## 运维与回滚

启动应用不自动升级数据库。显式迁移采用 MySQL 命名锁串行化；MySQL DDL 隐式提交，不能把多条 DDL 宣称为原子回滚。
初始表出现但无版本记录时拒绝自动接管。失败保留现场审查，不自动删表或 stamp。
本地入口只支持 status/upgrade；降级仅在本轮独立临时测试库演练，非空事件账本拒绝降级。真实后续回滚先备份和审批。

## 验证方式

跨平台后端行为测试、独立 MySQL 8.4.11 的迁移对比/回滚/并发集成、源码和完整依赖锁审计、真实本地健康检查。
参考 [SQLAlchemy Session](https://docs.sqlalchemy.org/en/20/orm/session_basics.html) 与 [Alembic 连接复用](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands)。
