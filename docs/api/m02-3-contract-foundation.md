# M02.3 第一批：接口与流式事件合同

本批是合同基础，不是整个 M02.3 完成。依据标准 E-01/E-03/E-10/E-11，保留 KF 内部协议和核心架构。

## 数据流

```text
未来 N3/N4 生产者（尚未接入）
  ↓ 先授权、校验 epoch、检查输出安全，正式结果先落库
平台事件 DTO 校验（本批已实现）
  ↓ 事件类型、字段类型、版本、长度、序号检查
SSE 编码（本批纯函数，无网络监听）
  ├─ 可恢复通知：cursor → id
  └─ 临时片段：不设置 id，不推进恢复游标
  ↓ JSON data + event + 空行；单帧上限 64 KiB
未来 SSE 连接 / 浏览器（尚未接入）
  ↓ 旧 epoch 丢弃、草稿展示、正式消息替换、snapshot 恢复
```

| 事件 | 功能 | 必要专用字段 |
|---|---|---|
| run.started | 平台 Run 获得执行资格 | run_id、cursor |
| run.progress | 白名单公开进度 | run_id、stage |
| answer.delta | 临时草稿片段 | run_id、token_seq、text |
| message.committed | 已持久化的正式消息通知 | cursor、message_id、message_seq、run_id（人工消息显式 null） |
| run.completed | 已保存本轮正式结果 | cursor、run_id、final_message_id |
| run.failed | 可恢复失败通知 | cursor、run_id、reason_code、next_action、command_id（可 null） |
| control.changed | 当前控制状态通知 | cursor、service_mode、active_run_id、assignment_id |
| resync_required | 必须读取正式快照 | reason、next_action=READ_SNAPSHOT |

公共字段：`schema_version=1`、`conversation_id`、`control_epoch`；整数最大值限定为浏览器可精确表示的范围，ID 不允许换行。字段限制是协议输入边界，不是内容安全检测或身份验证。cursor 由 N3 分配；本批不生成、不存储游标。

## 一次合成例子

1. N4 获得 R001 执行资格，发送 `run.started`。
2. 知识检索中发送 `run.progress(stage=RETRIEVING)`。
3. 普通问答允许流式输出时发送 `answer.delta(token_seq=1, text=您好)`；高风险内容不得在此阶段直出。
4. KF 返回 end 只代表子调用结束，**不能直接转 run.completed**。
5. N3 正式保存消息 M002 后，生产者才可发送 `message.committed`、`run.completed(final_message_id=M002)`。
6. 保存失败则不得发送完成事件；可归一化为 `run.failed(PUBLICATION_FAILED)`，客户端补查正式结果而非重做交易。

上述生产者状态守卫属于后续模块，本批只验证结构和编码，不能拿一个合法 M002 字符串证明数据库存在该消息。

## HTTP 与兼容边界

- OpenAPI 由当前 `create_app()` 导出，只包含 `/health/live`、`/health/ready`，不增加业务 URL。
- 本批保留既有 M02.1 HTTP 错误码；E-07 业务错误目录在后续合同批次统一，不悄悄改已有响应。
- schema v1 对生产输入严格拒绝额外字段，未知版本必须显式处理；未来扩展必需做消费者先行与新旧 fixtures 回归，不能假称已支持任意未来字段。
- 无授权 SSE 端点、无新 Cookie/Bearer 选择、无 KF 内部事件改动、无额外第三方依赖。
- 当前只测试生成漂移、八事件正例、非法字段/类型/版本、草稿游标、注入、失败与完成必填约束，以及真实应用工厂的健康 HTTP 响应。

## 文件与操作

- `packages/contracts/ics_contracts/`：Pydantic 合同与编码函数。
- `packages/contracts/generated/`：生成的 JSON Schema / OpenAPI；从源码生成，不手工编辑。
- `tests/contracts/`：离线合同及进程内 HTTP 测试，不访问真实订单或数据库。
- `scripts/check_contracts.py`：生成差异校验、Ruff、Bandit、pytest。
- `_local_artifacts/m02-3/tmp`、`_local_artifacts/caches/ruff`：项目内临时目录与缓存。
- GitHub 新启用 Linux/Windows 契约作业，复用已有哈希锁依赖；本机没有下载安装新依赖，没有启动/迁移任何容器。

待下一批：领域事件信封、业务操作合同清单、错误映射/权限/幂等/时间预算元数据和演进测试。93 条业务验收仍 NOT_RUN。

## 本批验收

实现提交 `eafd033`；[GitHub CI 34429732803](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34429732803) SUCCESS，双平台契约、基础与后端作业通过，Python 安全和四类镜像门禁通过；前端和手动 Milvus 作业按既有策略 skipped。本地 31 项契约、46 项后端测试通过，224 项基础检查通过（Windows 跳过 5 项符号链接测试）。保留两项既有测试依赖弃用警告，未以升级依赖扩大本轮范围。

首次负测确认 Pydantic Literal 对 Python `True == 1` 的处理会接受布尔版本；增加显式整数类型校验，布尔与浮点版本均已加入拒绝用例。本批所有新增源码、生成文件、文档和缓存均在 F 盘项目内，未下载新依赖。
