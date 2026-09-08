# ADR-0006 M02.1 网关应用与依赖存放

- 状态：Accepted
- 日期：2026-09-08
- 关联任务：M02.1
- 决策依据：用户授权开始 M02.1，并要求新增项目依赖放在 F 盘项目目录、保留既有 Docker 数据。

## 背景

M01 数据底座已验收，M02.1 首次新增应用运行源码，原来的后端与安全 CI 占位必须随之激活。
用户要求新增依赖随项目存放，保留已安装环境和 Docker 数据。

## 决策驱动因素

减少跨环境污染，准确表达健康语义，使失败与测试结果可追踪，并维持 KF 核心兼容边界。

## 决策

1. 首个运行模块为 apps/api-gateway/ics_gateway，采用 FastAPI 应用工厂和 lifespan。
2. M02.1 健康仅描述应用自身；数据库会话与迁移留在 M02.2，不连接旧 KF 或读取旧凭据。
3. HTTP 响应沿用标准 E-02/E-07，M02.3 才冻结完整跨模块机器合同和流式事件。
4. M02.1 只接受 dev/test、127.0.0.1，默认端口 28000，避免与已有 8000 或基础存储端口冲突。
5. 新 Conda prefix 为项目 `_local_artifacts/dependencies/platform`；Conda/pip 缓存、临时文件和
   审计证据均在 `_local_artifacts`。已有 Anaconda、Conda 环境、Docker 虚拟磁盘和 KF 不迁移。
6. 直接依赖按原平台基线 FastAPI 0.141.1、Uvicorn 0.52.4、Pydantic 2.13.5、settings 2.15.0；
   传递依赖以本阶段双平台验证及漏洞审计后的 requirements.lock 为准。KF 运行依赖独立。
7. 新增运行源码即激活后端测试和 Python Bandit/pip-audit 门禁，不能保持假 skipped。

## 备选方案

复用旧 Conda 环境会继续改变项目外依赖；使用默认 8000 端口会与旧 KF 冲突；
提前引入全部业务依赖会扩大 M02.1 范围。因此选择项目内新环境和独立本机端口。

## 结果与影响

不必提前引入 ORM、消息队列或模型。应用可独立测试启动、结束、错误脱敏、并发 ID 隔离、
健康失败、超时和文档模式。基础 JSON 日志仅满足 M02.1 排障；跨模块 trace/metric/audit 库归 M02.4。
Python 锁记录所有目标版本的 wheel 哈希并 binary-only 安装；Git 忽略环境、缓存、真实密钥和日志。
日常后端测试在 Windows/Linux 执行，源码和依赖安全门禁单独阻断。生产和局域网入口尚未开通。

## 安全与数据影响

只读环境配置；不读取原系统密钥，不写业务数据。错误与日志不返回用户输入、SQL、令牌或内部堆栈。

## 运维与回滚

使用项目内解释器运行 scripts/run_gateway.py，Ctrl+C 关闭本次网关。回滚只切换新网关代码，
M02.1 没有数据库迁移，既有 Docker 卷不需要操作。

## 验证方式

scripts/check_backend.py tests 与 security，加双平台基础 CI 和本机 HTTP 冒烟。
结果记录在 docs/testing/m02-1-gateway.md；93 条业务用例仍未执行。
