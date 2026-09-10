# M02.3 第二批：领域事件与业务规则目录

本批完成合同基础扩充，M02.3 整体仍 IN_PROGRESS；不开放业务路由，不连接 Redis 消费者，不执行交易。

## 三类交付

| 交付 | 事实来源 | 功能与边界 |
|---|---|---|
| 领域事件通用信封 | 既有 `ics_persistence.events.Event` | 直接导出 schema，不复制另一套模型，不修改 Outbox/Inbox 表或摘要算法 |
| `ticket.public_reply.created` v1 读取器 | `ics_contracts/domain.py` | 校验类型/版本、声明的生产者与聚合、公开性和原稿/分配引用；未知类型或版本抛 SCHEMA_UNSUPPORTED |
| 18 项操作、13 类错误策略 | `ics_contracts/policies.py` | 记录领域责任、授权条件、幂等、超时和重试动作；所有业务操作明确标 NOT_IMPLEMENTED |

原事件信封保留 M02.2 的 ID 长度/字符约束、UTC 秒级规范化、16 KiB payload 限制和默认版本 1，避免事件重放摘要改变。浏览器事件与内部事件不同合同，不强行统一二者 ID 约束。读取器限制整个输入为 32 KiB，只支持当前登记的一种载荷；通用信封 schema 校验通过不意味着任意事件类型可以消费。

本批合同读取器暂时单向依赖持久层已有纯模型，持久层不反向依赖合同包；不在导入阶段连接数据库。将来若移动该共享模型，必须保留旧导入路径和摘要兼容测试。

## 人工回复的数据流

```text
N7 保存原稿 + 本地 Outbox（未来领域实现）
  ↓ 同一 event_id 重投，不复制私密原文
通用事件信封校验 → 支持的类型/版本检查 → PublicReply 载荷检查
  ├─ 未支持/非法：交调用方持久隔离，不在这里 ACK
  └─ 合法：返回原 Event，保持摘要和 event_id
       ↓ 未来 N8/N3 核验真实服务身份、租户、原公开回复、分配与收件人权限
       ↓ 领域 Inbox + 正式消息 + Outbox 同事务提交
       ↓ 提交结果确认后才允许源消息 ACK
```

仅检查字符串 `producer=ticket-service` 或 `visibility=PUBLIC` 不是鉴权。该模块没有数据库提交、队列发布、ACK 或隔离存储；调用方不能把异常捕获后直接丢弃当成完成处理。

## 页面与聊天、失败恢复

- 页面 `commerce.submit` 与聊天 `workflow.confirm` 采用相同作用域幂等约束；预检不能直接产生退款等业务效果。
- 幂等作用域含 tenant、原发起人、operation、target_scope、key，不能被 Worker 服务账号替换。
- `COMMAND_RESULT_UNKNOWN`：提交 HTTP 202 / 查询 HTTP 200，使用 data 信封；不表示已成功，也不由 N4 猜测 N5 的权威状态。
- `DEADLINE_EXCEEDED`：查询原命令或对账，不对未知写操作盲重试。
- `PUBLICATION_FAILED`：只重发同一正式结果，不能重新执行业务。
- `ACCESS_DENIED` 支持 403 或为隐藏资源存在性而使用 404；具体领域决定，不泄露未授权资源。
- deadline 传播、恢复连接重新授权已记录；具体秒数和最大重试次数按既有标准留给 M17 冻结，不虚构当前硬件验收结果。
- 本批目录不替换 M02.1 已运行健康接口错误码，避免静默改变 HTTP 合同。

## 文件和验证

- 源码：`packages/contracts/ics_contracts/domain.py`、`policies.py`。
- 生成文件：`domain-envelope.schema.json`、`public-reply-v1.schema.json`、`operation-policies-v1.json`，均位于 `packages/contracts/generated/`。
- 测试：`tests/contracts/test_domain_policies.py`，覆盖存储摘要/重放身份兼容、未知版本、缺引用、私密载荷、时间类型、体积、写操作幂等和不确定结果策略。
- 统一入口：`python scripts/check_contracts.py`，继续在双平台契约 CI 中运行，不新增第三方依赖。
- 本地契约测试共 49 项通过；远端结果在台账收录。所有新文件和临时缓存仍在 F 盘项目目录，本轮不启动、停止、迁移任何服务，也不修改原 KF 或旧项目。

## 仍待完成

每个业务操作的完整请求/响应 DTO、正式 URL、分页/游标、确认载荷、金额类型、权限矩阵细化及新旧版本 fixtures 尚待后续批次。当前机器目录不是 18 个可调用 API，类型检查不是授权实现；93 条业务验收仍 NOT_RUN。

## 验收证据

实现 `642acf1` 已推送；[GitHub CI 34430866686](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34430866686) SUCCESS。双平台契约/后端/基础、Python 安全和四类镜像作业通过；前端与手动 Milvus 作业按既有策略 skipped，不算本次运行通过。本地 49 项契约、46 项后端测试通过，224 项基础检查通过（Windows 跳过 5 项），两项既有测试依赖弃用警告保留。
