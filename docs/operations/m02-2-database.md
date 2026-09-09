# M02.2 数据库与事务基础：运行及行为记录

日期：2026-09-09。开发根目录：`F:\heima\ai\python\project\i`。

## 本次建立的链路

```text
本机 Gateway（可选 --with-database）
  └─ 校验新平台容器所有权、镜像、端口和非 root 账号
      └─ SQLAlchemy 有界连接池 → 新平台 MySQL / ics_dev
          └─ 健康探针核对 platform_alembic_version；失败返回 503

未来领域处理器（本步不实现业务）
  └─ 独立 Session / 显式短事务
      ├─ 本领域事实及审计
      └─ enqueue → platform_outbox
          ├─ 失败：两者一起回滚
          └─ 提交：事件可被认领
              └─ claim / SKIP LOCKED → 租约 + token
                  ├─ 传输持久受理后 acknowledge → PUBLISHED
                  ├─ 失败 retry → 延迟重试；耗尽 → DEAD 保留
                  └─ 租约超时 → 新 token 认领，旧 token 不能 ACK

未来消息消费者（队列与业务处理器尚未接入）
  └─ 验证来源、租户、类型/schema
      └─ 同一本地事务：Inbox 唯一占位 + handler 的本领域写入
          ├─ 同 ID / 同内容：返回原 result_ref
          ├─ 同 ID / 异内容：冲突，不覆盖
          └─ 失败：效果和 Inbox 一起回滚，提交成功后才可确认源消息
```

例：未来“保存客服公开回复”事务成功，才能留下对应事件；投递成功但响应丢失可再次投递原 event_id，消费者返回原结果。当前测试使用 synthetic 记录验证上述机制，没有创建真实工单、退款或客服回复。

Outbox 的重复事件检查不代替业务命令幂等；生产者必须先按 E-04 在本领域处理稳定 command_id/幂等键，不能先重复执行业务再仅依赖 enqueue 返回 False。

## 技术、原理与作用

| 技术 | 当前版本 / 作用 |
|---|---|
| SQLAlchemy | 2.0.52；连接池、SQL 参数化、独立 Session、提交/回滚 |
| Alembic | 1.19.2；冻结迁移 revision m02_2_0001，记录表结构版本 |
| PyMySQL + RSA 支持 | 1.2.0；连接 MySQL 8.4 的认证/读写；不降低现有认证插件 |
| Outbox | 业务事实与待发送事件同事务，避免“业务提交但事件丢失” |
| Inbox | 消费记录与实际效果同事务，用唯一键抵御重复投递 |
| SKIP LOCKED / 租约令牌 | 并发认领互不抢同条记录，失联任务可恢复、旧任务不能误 ACK |

详见 [ADR-0007](../decisions/ADR-0007-sql-transactions-and-event-foundation.md)。当前仍是开发合成数据、非生产 TLS 配置；未完成 M03 身份权限。

## 写入与下载清单

- `packages/persistence/ics_persistence/`：database、schema、events、outbox、migration 与冻结迁移文件。
- `scripts/database_local.py`：只对已验证的 M01 MySQL 执行状态/升级。
- `scripts/check_mysql.py`：本轮独立临时容器集成门禁，结束时核对唯一标签后精准清理。
- `apps/api-gateway/ics_gateway/app.py`、`scripts/run_gateway.py`：显式选择 MySQL 健康依赖，关闭连接池。
- `tests/backend/test_persistence.py`、`tests/integration/test_m02_mysql.py`：失败、回滚、去重、版本、真实锁测试。
- `.github/workflows/ci.yml`、`scripts/verify_ci.py` 与质量脚本：双平台测试扩展；MySQL 镜像构建作业增加真实集成，不改变扫描阻断规则。
- README、目录/边界、ADR、台账、验收、Makefile、变更日志随代码同步。

解释器不新建、不迁移：`_local_artifacts/dependencies/platform/python.exe`，Python 3.12.14。
新增 9 个依赖：SQLAlchemy 2.0.52、Alembic 1.19.2、PyMySQL 1.2.0、greenlet 3.5.5、Mako 1.4.1、MarkupSafe 3.0.3、cryptography 50.0.1、cffi 2.1.1、pycparser 3.0。
完整解析同时更新 3 个工具传递依赖：filelock 3.32.5→3.32.6、pip-api 0.0.34→0.0.35、platformdirs 4.11.7→4.11.8。纳入完整哈希锁和审计，不修改旧 KF 依赖。
运行锁 24 项，合并运行/测试工具锁 61 项；官方 PyPI wheel SHA-256 校验后安装。
下载 URL、体积、哈希、元数据及安装报告均在 `_local_artifacts/m02-2/`；缓存仍为 `_local_artifacts/caches/pip`、`pip-audit`、`ruff`，临时测试目录在 `_local_artifacts/m02-2/tmp`。
质量脚本沿用项目内 `_local_artifacts/m02-1/tmp`，同样在 F 盘。没有新增 C 盘安装目录，也没有处理上一轮被安全检查拦截的 C 盘缓存。

## 数据写入与未做的行为

- 独立临时 MySQL：使用现有受审镜像、随机新容器名与标签、随机本机端口、随机合成账号密码；数据在新容器 tmpfs，不挂已有卷。测试创建事件表与 synthetic_effects，仅清理本轮容器及其合成数据，不可恢复但不含业务数据。
- 新平台 MySQL：只增加 platform_outbox、platform_inbox、platform_alembic_version；后两类事件记录初始为空，版本记录为 m02_2_0001。
- 不升级/重建/停止原有 Docker 容器，不迁移 Docker 数据，不连接原 KF 数据库，不改参考压缩包。
- 不增加资金动作、领域业务表、队列消费者或自动迁移启动钩子；不运行原来的 93 条业务验收。

## 运行命令

项目根目录，使用上述解释器（下例 python 指向它）：

```powershell
python scripts/check_backend.py tests
python scripts/check_backend.py security
python scripts/check_mysql.py
python scripts/database_local.py status
python scripts/database_local.py upgrade
python scripts/run_gateway.py --with-database
```

普通 `run_gateway.py` 保留无数据库模式；加参数才读取新平台的非 root 凭据。不得同时启动两个占用同一端口的网关。
默认 `127.0.0.1:28000`，`/health/live` 仅检查进程；带数据库模式下 `/health/ready` 成功返回 scope=application+database，MySQL 断连/迁移缺失返回 503。这不代表五类存储、RAG 或业务可用。

## 实施中修正

1. Windows 默认编码无法读取 PyPI 描述中的 UTF-8 字符：生成器改显式 UTF-8，没有更换包来源或跳过哈希。
2. SQLite 默认 legacy transaction 模式导致嵌套保存点提前生效：测试设置 autocommit=False；真实 MySQL 独立验收，不能据 SQLite 单测推断锁行为。
3. MySQL DDL 隐式提交与版本记录事务不同：迁移显式提交版本记录、命名锁串行化，失败保留现场。
4. Inbox handler 异常即便被外层捕获，也必须回滚占位及效果：增加整体保存点并测试，防止留下空 result_ref。

本地与远端结果见 [M02.2 验收](../testing/m02-2-database.md)。

本轮核对上一阶段网关 PID 27980 的解释器与启动命令后，仅替换这个本机网关；新实例 PID 35480，参数 `--with-database`。
日志：`_local_artifacts/m02-2/gateway.stdout.log`、`gateway.stderr.log`。既有 Docker 服务没有重启。
