# M02 全阶段验收与行为记录

日期：2026-09-10。当前：M02.1–M02.4 全部 DONE，本地与远端验收通过。

## 范围与结论

| 阶段 | 本地交付 | 验证 |
|---|---|---|
| M02.1 | FastAPI 工厂、健康、错误返回与关联标识 | 实际回环 HTTP + MySQL readiness + 响应 trace 与日志一致 |
| M02.2 | SQLAlchemy 短事务、Alembic、Outbox/Inbox | 原测试保留；真实 MySQL 迁移/并发/重连/回滚验证 |
| M02.3 | OpenAPI、8 类平台事件、18 项业务设计、6 项媒体扩展、版本冻结 | 169 项契约通过；旧基线与扩展未变；SSE 通过 ASGI 分帧集成验证 |
| M02.4 | 网关追踪/JSON 日志/有界指标、事务审计落库 | 后端总计 63 项；真实 MySQL 总计 9 项通过 |

M02 的完成是“后端骨架与共享合同可用”，不等于电商 V1 全部业务完成。正式网关仍只有两个健康端点。SSE 使用测试专用 ASGI 应用验证编码、逐帧发送、取消与中途失败，不开放未授权聊天接口。M03 身份权限、后续 RAG/业务工作流/前端和 93 条业务用例仍待实施。

## 完整数据链路

```text
HTTP 请求
  → RequestContext：校验 request_id，生成服务端 trace_id
  → ContextVar：当前异步请求可读取追踪上下文
  → 路由 / 健康检查 / 后续业务调用
  → 响应发送：关联 Header，不缓冲 SSE body
  → 完整结束 / 取消 / 失败分别记录
  → JSON 日志 + http 固定标签指标，恢复原上下文

可信领域调用（M03 后取得授权上下文）
  → Database.transaction
  → 业务写入 / Outbox 写入 + append_audit
  → 全部成功才由事务所有者 commit
  → 任一失败向外抛出，所有同事务写入 rollback
```

审计不是自动记录每个健康请求：未认证请求不得伪造 actor/tenant。后续领域在同一事务显式调用审计端口；本批通过合成事件演示其事务语义。诊断日志和安全审计用途不同：诊断输出失败不改写已发送响应，middleware.diagnostic_failures 记录失败次数；审计写失败不得吞掉后继续提交业务。

## 实现细节及边界

- 网关每实例一个 Metrics；只使用静态 `http` 标签及 SUCCEEDED / FAILED / CANCELLED，避免 URL、订单号或客户标识造成指标膨胀。`app.state.metrics.to_json()` 提供有界进程内拉取输出，不开放公网 `/metrics`。重启计数清零，跨进程聚合/告警由后续部署观测实施。
- trace 是服务端生成的关联 ID，不宣称完整 OpenTelemetry/W3C 分布式 span；外部 trace/tenant/actor Header 不作为身份依据。上下文在异常与取消后恢复，流结束前不复用给另一请求。
- 日志只写关联 ID、方法、路由模板、状态、耗时、结果及是否完整发送；不写原始 query、请求体、认证凭据或异常内容。`status` 在异常时是处理失败状态，不能据此声称已发送的 HTTP 200 被改成 500；`response_complete`/`outcome` 描述发送结果。
- 新 `platform_audit` 以 tenant_ref/event_id 为联合身份，保存白名单 JSON 及 SHA-256。同身份同内容重试返回 False，不重复写；不同内容抛 AuditConflict。append_audit 成功仅表示当前事务内写入，必须等外层 commit 才持久化。
- 摘要用于冲突检测，不是防管理员篡改或 WORM 证据；没有宣称合规审计平台已完成。审计读取权限、独立保留/归档、不可变存储和告警由后续权限/运营阶段实现，当前不提供公开审计查询。
- Alembic 新增 `m02_4_0002`，只创建审计表，不改旧迁移。降级前检查审计及事件表，任何历史存在则拒绝删除。MySQL DDL 隐式提交，不声称多语句 DDL 可原子回滚。

## 实际修改与位置

根目录：`F:\heima\ai\python\project\i`。

- `apps/api-gateway/ics_gateway/app.py` / `middleware.py`：追踪上下文、实例指标、流完成/取消结果与诊断失败隔离。
- `packages/observability/ics_observability/core.py`：有界 JSON 指标导出；`audit.py`：显式事务审计端口。
- `packages/persistence/ics_persistence/schema.py`、`version.py`、`migration.py` 及新迁移 `migrations/versions/m02_4_0002_audit.py`：审计表与版本守卫。
- `scripts/run_gateway.py`、`check_contracts.py` 与测试导入配置：接入共享观测包，不修改冻结合同。
- `scripts/check_gateway_local.py`：随机回环端口启动本次专属网关子进程，真实探测后终止本次子进程；不按端口或进程名结束其他服务。
- `scripts/check_backend.py`：新增探针纳入安全检查；新增后端集成测试及真实 MySQL 第 9 项审计测试。
- 本说明、任务台账、CHANGELOG 与包 README 同步。

没有新增或升级依赖；复用项目内 Python 3.12.14、FastAPI/Starlette、SQLAlchemy/Alembic、pytest、Ruff、Bandit、pip-audit。新文件均在 F 盘项目；测试临时文件及工具缓存使用 `_local_artifacts` 既定目录。安全数据库刷新可能更新项目内 pip-audit 缓存，未安装系统服务。

开发库已通过 `database_local.py upgrade` 在核对新平台容器、镜像、端口和用户归属后升级，状态 READY；新增审计表，不迁移或清空旧数据。MySQL 集成测试使用独立临时容器与合成 tmpfs 数据，完成后仅清理该容器及合成数据，无卷删除。实际网关联测进程已停止，没有留下新监听端口。

原 KF / 原电商代码、参考归档和既有 Docker 数据位置未改动。GitHub 继续按既有规则在 runner 上下载依赖、构建扫描镜像，不部署到本机。

## 验证证据

- `check_backend.py tests`：63 passed。
- `check_contracts.py`：169 passed，生成一致性与两份冻结基线通过。
- `check_mysql.py`：9 passed，真实 MySQL；包含审计与事件同事务回滚、同内容并发重试、冲突回滚、重连可读。
- `database_local.py upgrade`：READY；`check_gateway_local.py`：真实 HTTP + MySQL + trace + JSON 日志 PASS，专属子进程已退出。
- `ci.py`：224 项基础测试运行成功，Windows 跳过 5 项符号链接测试；48 条标准引用和 93 条用例结构检查有效，用例业务状态不改变。
- Bandit 与两份依赖锁 pip-audit 通过。新本机探针的 B404/B603 两处告警经检查限定为“当前解释器 + 固定项目脚本 + 固定参数、无 shell、专属子进程句柄”，作局部带理由标注；未全局关闭规则，未忽略任何依赖漏洞。
- 两项既有 Starlette/anyio 弃用警告保留；不影响本次通过，不为消除警告升级锁定依赖。

远端签收结果在 CI 完成后补记。未确认前不标记 M02.4 DONE。

远端复核修正：首次实现 `c98ae47` 的运行 `34454184776` 在基础格式检查失败。原因是新增安全审阅注释后 import 区缺少 Ruff 要求的空行；本地重现后按既有 formatter 修正并重新通过基础检查。未跳过或放宽门禁，完整 CI 随修正提交重跑。

## 最终签收

实现 `c98ae47`、格式修正 `aaa8058` 已推送 `origin/codex/v1-greenfield`；[GitHub CI 34454383386](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34454383386) 于本轮确认 SUCCESS，未完成/失败作业均为零。双平台基础、后端、契约、Python 安全以及四类镜像构建安全检查通过。前端与手动 Milvus 全源码任务按既有策略 skipped，不计为本次执行通过。

M02 全阶段正式收口；上文“等待 CI”属于过程记录。后续是 M03 身份、租户与权限。本次没有提前实施 M03，也未将 93 条业务验收改为通过。
