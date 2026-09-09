# api-gateway

统一外部入口和协议边界。

- 负责：认证、租户上下文、限流、关联 ID、输入校验、协议适配、响应与错误码统一。
- 拥有数据：不拥有业务事实表，仅保存必要的网关配置和审计信息。
- 禁止：承载订单规则、RAG 检索、售后状态机等领域逻辑。
- 已实现 M02.1：FastAPI 应用工厂、生命周期、统一成功/错误响应、请求关联 ID、网关自身健康检查。
- 认证、租户、限流仍为 M03 起的目标能力，当前只监听本机回环地址。

## 本地运行

项目根目录执行（PyCharm 选择同一个解释器，运行 `scripts/run_gateway.py`）：

```powershell
& .\_local_artifacts\dependencies\platform\python.exe scripts/run_gateway.py
```

默认地址 `http://127.0.0.1:28000`；`/docs` 为 Swagger UI，`/openapi.json` 为本地模式定义。
Swagger 的默认 JS/CSS 来自 CDN，离线时直接读取 `/openapi.json`；M02.3 再冻结完整机器合同。

默认仅读取 `ICS_GATEWAY_*` 环境变量，不自动读取根目录历史 `.env` 或 M01 密钥。
M02.2 增加 `--with-database`：校验新平台容器/镜像/端口后读取 M01 非 root MySQL 凭据，注册连接与迁移健康检查；不执行自动迁移。
配置示例在本目录 `.env.example`。dev/test 被支持，prod 和非回环监听被拒绝。

## 健康语义

- `GET /health/live`：进程能响应，不依赖数据库。
- `GET /health/ready`：应用 lifespan 已启动且已注册检查通过；未启动、检查异常/超时返回 503。
- 默认无数据库模式返回 `scope=application`；显式带数据库模式返回 `scope=application+database`，失败为 503，不宣称五存储或业务可用。
- M02.2 管理 SQLAlchemy 连接生命周期；网关不直接承载订单事务。迁移使用独立 `scripts/database_local.py upgrade`。

响应和排障见 [M02.1 HTTP 说明](../../docs/api/m02-1-gateway.md)，操作及新增依赖位置见
[M02.1 行为记录](../../docs/operations/m02-1-implementation-log.md)。
