# M02.1 网关验收

本地验收已通过，等待本提交 GitHub 远端门禁完成。

| 检查 | 本地结果 |
|---|---|
| 后端行为测试 | 24 passed，包含生命周期、并发关联 ID、失败与超时 |
| Python 包一致性 | pip check 无破损依赖 |
| Ruff | 应用与测试静态检查、格式检查通过 |
| Bandit | 应用与启动脚本检查通过，无跳过规则 |
| pip-audit | 15 项运行锁与 52 项合并工具锁均无已知漏洞，无忽略项 |
| 基础门禁 | 209 项测试，Windows 按现有权限跳过 5 项符号链接；Linux 必须执行 |
| 真实 HTTP | /health/live、/health/ready、/openapi.json、/docs 为 200；未知路径为脱敏 404 |
| 本机进程 | 新网关 127.0.0.1:28000，创建时 PID 27980；未修改 Docker |

健康明确返回 scope=application。HTTP 实测不是数据库连接或业务闭环验收。
测试运行保留 Starlette 对 httpx 与 AnyIO BlockingPortal 的两条弃用提示；未屏蔽警告，
当前组合测试通过，升级测试客户端时重新生成锁并回归。默认 Swagger JS/CSS 需要 CDN，
离线可使用本地 /openapi.json；未把页面 HTTP 200 冒充离线 Swagger 前端资源已加载。

验收范围：应用独立实例、生命周期就绪/关闭、JSON 响应、错误脱敏、请求关联、并发隔离、
健康扩展失败与有界超时、配置拒绝、基础 OpenAPI 和本机 HTTP。
CI 要求 Windows/Linux 后端测试及 Bandit/pip-audit 为真实阻断式作业。

M02.2 ORM/迁移、M02.3 完整机器合同、M02.4 观测库和 93 条业务验收不在本次完成范围。
