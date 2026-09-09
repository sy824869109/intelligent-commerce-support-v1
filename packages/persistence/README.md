# SQL 持久化基础设施（M02.2）

`ics_persistence` 提供有界连接池、短事务、版本迁移和 Outbox/Inbox 原语。
不依赖 apps，不包含订单、会话或权限规则，也不替领域服务发起跨表写入。
当前 `platform_outbox` / `platform_inbox` 是开发基础事件账本，所有操作显式限定 producer/consumer 和 tenant。
这不是 M03 身份授权；后续领域必须从可信上下文获得这些值。物理拆库时各所有者采用独立账本和迁移线，不能用此包跨库提交。

依赖暂随平台运行锁安装。完整运行、边界和验收见 `docs/operations/m02-2-database.md`。
