# M03 身份、租户与权限：实施及验收

日期：2026-09-10。状态：本地实现/功能测试完成；最终安全、开发库部署与远端 CI 待签收。

## 四项交付

| 任务 | 实现 |
|---|---|
| M03.1 | 组织、租户、用户、成员、角色、权限、客服组及组员；复合外键约束租户关系 |
| M03.2 | 登录、刷新轮换、重放吊销、退出、修改密码及全账号会话吊销；密码哈希、请求限制和持久化限流 |
| M03.3 | Bearer 身份依赖、Origin/JSON/大小/接收期限边界、RBAC + 当前资源归属/客服组依赖 |
| M03.4 | 三角色 × 订单/知识库/工单的服务层与真实 HTTP 依赖矩阵；MySQL 并发和约束测试 |

## 数据流

```text
用户名 + 密码 + 选择的租户（仅是登录目标）
  → Origin / JSON / 4 KiB / 10 秒接收限制
  → IP 与账号限流 → scrypt 校验
  → 当前用户、租户与成员有效性检查
  → 同事务创建会话、令牌摘要和审计 → 返回原始令牌一次

Authorization: Bearer <access_token>
  → SHA-256 查令牌 → 当前会话/用户/租户/成员检查
  → 数据库角色权限 → 领域资源真实租户/归属/客服组
  → 放行领域处理，或统一拒绝（资源不存在/无权均为 404）

刷新令牌 → 锁定会话 → 当前令牌未使用？
  是：作废旧令牌 → 创建新令牌摘要 → 提交
  否：吊销会话 + 审计 → 提交 → 返回 401
```

成员停用或降权会吊销该租户内此人的会话；密码修改吊销该用户所有租户会话。客服组变化每次授权重新查表，不需等待访问令牌过期。当前 ADMIN 也不能跨租户，CUSTOMER 不能读取同租户另一客户的订单/工单，AGENT 只能访问所属组的私有资源；客户可读知识还须已发布且对客户可见。

## 实际接口

启动身份模式才注册以下端点；全部使用既有 request_id / trace_id / data 或 error 信封。

| 方法 | 路径 | 身份要求 |
|---|---|---|
| POST | /api/v1/auth/login | 无先验会话，验证凭据及租户成员关系 |
| POST | /api/v1/auth/refresh | JSON 刷新令牌；非 Cookie |
| GET | /api/v1/auth/me | 当前有效 Bearer 会话 |
| POST | /api/v1/auth/logout | 当前会话，JSON 空对象 |
| POST | /api/v1/auth/password | 当前会话与原密码 |
| POST | /api/v1/auth/members | 当前租户管理员创建新账号与成员关系 |
| PATCH | /api/v1/auth/members/{user_id} | 当前租户管理员；不得禁用最后一名可用管理员 |
| POST | /api/v1/auth/groups | 当前租户管理员 |
| PUT | /api/v1/auth/groups/{group_id}/members | 当前租户管理员，目标用户/组必须在本租户 |

OpenAPI：`docs/api/m03-identity.openapi.json`，包含 Bearer 安全方案和错误响应。`export_identity_openapi.py` 检查漂移，已纳入双平台后端 CI。默认无数据库工厂继续只暴露健康接口，原 M02 冻结 OpenAPI 与合同没有覆盖或改写。

错误：认证失败/过期/吊销为 401；资源无权/不存在为 404；来源拒绝 403；格式与密码策略 422；账号冲突/最后管理员保护 409；超大请求 413、不支持媒体 415、接收超时 408；限流 429 附 Retry-After。数据库/内部异常使用现有脱敏 500，绝不回退到 Header 身份。

默认认证中间件对身份模式的所有 `/api/` 路径生效，仅 POST 登录/刷新豁免；后续路由即使漏写认证依赖，也不能被匿名调用。它不替代资源权限检查，领域读写仍必须使用下面的授权依赖。

## 领域接入规则

`require_resource(action, loader)` 在同一事务调用可信 loader 与当前权限校验，然后才允许处理器返回数据。loader 应按数据库中的实际资源创建 Resource，不能直接使用 JSON 提供的 tenant_id/owner_id/group_id。写业务必须在其所属事务内再次授权，再执行状态/确认等业务守卫。

本阶段没有订单、知识或工单正式业务查询端点；授权集成测试创建测试专用 SQL 资源和路由，不将其发布到正式应用。既有 93 条跨模块业务验收不因这些测试自动变成通过。实际 SSE 连接尚未实现；M03 冻结 Header 方式与每次连接重新验证要求，后续流实现须在撤权与关键发送/副作用前复查。

## 首次使用

在项目根 `F:\heima\ai\python\project\i` 的项目 Conda 解释器环境中运行：

```powershell
python scripts/database_local.py upgrade
python scripts/bootstrap_identity.py --username admin
python scripts/run_gateway.py --with-database
```

首次初始化脚本要求本机交互输入并二次确认管理员密码；不会接受命令行明文密码，不创建默认密码，不把密码写进文件。它拒绝已初始化的身份库，应由运维串行执行一次。成功后显示非秘密的 tenant_id，供登录选择。当前代理与服务保持 127.0.0.1；不要把 HTTP Bearer 暴露到局域网明文链路。

本轮**没有替用户设置真实管理员密码，也没有向开发库植入演示账号**。所有测试账号仅在隔离数据库内。实际管理员首次密码由用户自行确定，这是运行初始化，而不是未实现的账号功能。

## 文件与行为清单

新增：

- `packages/identity/ics_identity/`：passwords.py、service.py、包入口及 README。
- `packages/persistence/ics_persistence/identity_schema.py` 与迁移 `m03_0003_identity.py`：12 张身份相关表；静态角色权限种子，没有密码种子。
- `apps/api-gateway/ics_gateway/identity.py`：真实路由、认证依赖、资源授权依赖和请求边界。
- `scripts/bootstrap_identity.py`、`export_identity_openapi.py`、M03 OpenAPI、测试与本文、ADR-0009。

修改：网关工厂/设置、启动脚本、后端检查脚本、审计动作白名单、迁移头及元数据入口、后端/真实 MySQL 测试导入与用例、README/台账/变更记录。新身份包不依赖 KF，未修改 KF 核心或参考归档。

复用现有 Python 3.12.14、FastAPI/Pydantic、SQLAlchemy/Alembic、标准库 scrypt/secrets/hashlib、pytest/Ruff/Bandit/pip-audit。**无新依赖安装或版本升级。** 文件、缓存与临时数据继续在 F 盘项目 `_local_artifacts` 既定目录；不迁移既有 Docker 数据。

真实 MySQL 测试使用拥有本轮标识的临时容器和合成 tmpfs 数据；完成后只移除该测试容器及合成数据，没有删除卷。过期会话清理端口默认最多 100 条，只删除已过绝对期限的会话及令牌，保留审计；本轮未对开发库调用清理。

## 验证状态

- 后端第一轮通过 87 项（含参数化权限矩阵）；最终结果随后补记。
- M02 合同 169 项继续通过，旧生成制品及冻结基线不变。
- 真实 MySQL 12 项通过：迁移往返、并发刷新唯一成功/重放全会话吊销、组权限变更、跨租户拒绝、外键约束、拒绝破坏性降级。
- 基础检查 224 项运行成功，Windows 跳过 5 项符号链接测试；93 条用例只作结构校验。
- Bandit 源码检查通过。运行依赖锁扫描无已知漏洞；工具依赖锁的本地 PyPI 查询多次连接中断，尚不能将该本地检查记为通过，远端完整安全作业将再次检查两份锁。
- `Bearer` 协议名称曾触发密码常量误报，已抽出具名公共协议常量；没有留下新的 nosec 例外或关闭安全规则。

开发库迁移、真实启动探针及远端 CI 最终结果待补记；未全部通过之前 M03 保持 IN_PROGRESS。两项既有 Starlette/anyio 弃用警告保留。

本地安全重试结果：原 PyPI 查询恢复后，完整 check_backend.py security 已通过，两份锁均未发现已知漏洞；没有改扫描源、关闭规则或忽略漏洞。前述网络失败作为过程证据保留。
