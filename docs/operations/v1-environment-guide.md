# V1 环境搭建说明与操作入口

> 当前为集中准备阶段，最终状态以验收记录为准。环境能运行不等于业务已实现；M04 及后续业务仍按教学节奏推进。

## 1. 你真正需要理解的四层

```text
PyCharm：写代码、调试
  ├─ 已有 V1 Conda → Python → FastAPI / LangChain / 数据库客户端 / 测试
  ├─ 项目 Node.js → pnpm → Vue 3 / Vite / TypeScript / 浏览器测试
  └─ Docker Desktop
       ├─ ics-v1-dev：MySQL、Redis、etcd、SeaweedFS、Milvus
       └─ ics-v1-tools：TLS 入口、指标、追踪、日志与可视化（准备中）
```

Conda 不是数据库，也不是服务器。它提供隔离的 Python 解释器和包；Docker 运行需要长期驻留的基础服务。PyCharm 是操作这些工具的开发界面。

## 2. 唯一开发解释器

`F:\heima\ai\python\day01\Anaconda\envs\intelligent-commerce-support-v1\python.exe`

PyCharm 中选择已有 Conda 环境，不再点“新建”。项目 `.idea/misc.xml` 已引用这个名称。业务与 RAG 都在此环境；`kfRag` 等其他环境不变。终端打开项目后执行：

```powershell
. .\scripts\enter_environment.ps1
python --version
python -c "import sys; print(sys.executable)"
```

该脚本只调整当前终端的路径与缓存位置，不改全局 PATH、不切换其他项目。Conda 的全局安装继续使用已有 Anaconda；不会重复安装它。

## 3. 每项技术为什么存在

| 技术 | 原理与职责 | 本项目用来做什么 |
|---|---|---|
| Python 3.12 / Conda | 解释执行；隔离依赖 | 统一后端、RAG 和测试解释器 |
| FastAPI / Uvicorn | 定义 HTTP 接口 / 实际监听和调度请求 | 网关、鉴权、后续 SSE 与内部服务 |
| Pydantic | 把外部数据验证为确定结构 | 拒绝不合法参数、管理配置 |
| SQLAlchemy / Alembic / PyMySQL | 数据访问 / 表结构版本 / MySQL 连接协议 | 事务、权限与后续业务表 |
| MySQL | 持久化关系数据、事务 | 用户、订单、会话、工单的事实来源 |
| Redis | 内存数据结构 | 后续缓存、限流、短期状态、Streams；不是唯一事实来源 |
| SeaweedFS S3 | 文件对象存储接口 | 原始知识文件与 Milvus 对象；已替换早期 MinIO 选型 |
| Milvus / etcd | 向量检索 / 集群元数据 | 稠密向量和 BM25 混合召回；etcd 不直接服务前端 |
| LangChain | 统一模型、文档与检索适配接口 | 保持 KF 的核心检索分层，不负责修改订单或退款 |
| BGE-M3 | 文本编码成 1024 维向量 | 语义召回；KF 的稀疏路由使用 Milvus 内置 BM25 |
| BGE-reranker-v2-m3 | 同时读取问题与候选段落并评分 | 把更相关的检索结果排在前面 |
| PyTorch / Transformers / Sentence Transformers | 张量运算 / 模型加载 / 向量与重排封装 | 本地模型推理；当前 CPU 基线，不改 GPU 驱动 |
| Docling / pypdf / Office 解析库 | 解析文件、提取文本与结构 | 后续知识上传与解析；扫描件还需要 OCR 资产和专项验证 |
| Vue 3 / TypeScript | 组件化界面 / 静态类型 | 用户端、客服台、管理后台 |
| Vite / pnpm | 编译打包 / 锁定安装依赖 | 三端共享工具链；当前只准备环境 |
| Pinia / Vue Router / Element Plus | 状态 / 页面路由 / UI 组件 | 避免每个页面重复造基础设施 |
| Nginx / TLS | 统一入口、反向代理、加密连接 | 后续同源页面、API、SSE；现在只准备本机入口 |
| OpenTelemetry / Prometheus / Tempo / Loki / Grafana | 采集 / 指标 / 追踪 / 日志 / 展示 | 看请求走到哪里、慢在哪里、失败在哪里 |
| pytest / Playwright / pip-audit | 自动测试 / 真浏览器 / 已知漏洞检查 | 减少后续教程中的环境回归 |

## 4. 文件放在哪里

项目根目录：`F:\heima\ai\python\project\i`。

| 位置（相对于项目） | 内容 | 是否上传 GitHub |
|---|---|---|
| `deploy/dev-environment/` | 锁文件、非秘密配置、前端测试夹具 | 是 |
| `scripts/*environment*` | 安装、启动、检查入口 | 是 |
| `_local_artifacts/dependencies/node` | Node.js 解压运行时 | 否 |
| `_local_artifacts/dependencies/pnpm` | 项目包管理器 | 否 |
| `_local_artifacts/models` | 固定版本的模型文件 | 否 |
| `_local_artifacts/caches` | pip、uv、pnpm、浏览器、模型下载缓存 | 否 |
| `_local_artifacts/environment` | 下载文件、检查报告、本地秘密、监控数据 | 否 |
| `deploy/compose/secrets` | M01 既有开发数据库与存储秘密 | 否 |

Conda 环境本体按你最新指定，放在已有 Anaconda 的 V1 目录，这是“新文件随项目”的明确例外。Docker 既有镜像和数据仍由原有 Docker 存储位置管理，没有迁移。

## 5. 我怎样安装，而不是让你逐个装

1. 盘点现有服务、端口、解释器、内存、显存与剩余磁盘。
2. 先确定整个依赖组合，再生成精确版本和 SHA-256 锁；避免先装 A 再用 B 覆盖 A。
3. 所有 Python 包装进已有 V1；Node 下载先核验官方 SHA-256，再在项目内解压，不全局安装。
4. 模型固定仓库、revision、文件范围及哈希。原 KF 中可匹配官方哈希的 BGE 文件只读复用到新目录；其余从固定官方版本获取。
5. 存储服务复用 M01 已审查镜像；监控独立配置和端口。真实密钥只放忽略目录，不进日志和仓库。
6. 分别验证安装、导入、运行、跨服务数据流、异常与清理；成功安装不直接算验收成功。

复现入口：`scripts/setup_v1_environment.ps1 -IncludeFrontend`。它要求现有 V1 和 uv 已存在；不会偷偷新建解释器。网络下载失败应保留现场并重试，禁止省略哈希校验。

## 6. 常用检查与服务入口

先进入项目并执行 `enter_environment.ps1`，再使用：

```powershell
python scripts/local_infra.py up
python scripts/local_infra.py health
python scripts/database_local.py status
python scripts/check_environment.py runtime
python scripts/check_environment.py models
python scripts/environment_services.py health
python scripts/check_environment.py telemetry
python scripts/run_gateway.py --with-database
```

最后一个命令在当前终端运行后端；关闭前按 Ctrl+C 正常退出。M01 工具的 `up` 会检查归属和密钥，不会启动 KF。监控组首次准备流程和镜像审查需通过后才可启动，不能把配置文件存在当作服务已验收。

## 7. 端口与访问边界

| 能力 | 本机端口 | 说明 |
|---|---:|---|
| MySQL / Redis | 23306 / 26379 | 已有开发底座 |
| S3 / Milvus | 28333 / 29530 | 已有开发底座 |
| 后端网关 | 28000 | 启动后提供已实现的健康和鉴权接口 |
| HTTPS 入口 | 28443 | 准备中；项目本地证书，不自动加入系统信任 |
| Grafana / Prometheus | 23000 / 29090 | 准备中；Grafana 不允许匿名访问 |
| OTLP gRPC / HTTP | 24317 / 24318 | 准备中；只接收本机诊断数据 |
| Tempo / Loki / Collector 健康 | 23200 / 23100 / 23333 | 准备中；诊断端口 |

端口默认仅 `127.0.0.1`。此阶段不修改防火墙、不公开管理面。局域网业务发布还需实际页面、访问域名或 IP、可信证书、授权和发布验收；这不是“已具备完整电商平台”。

## 8. 云端模型配置

把 `deploy/dev-environment/model.env.example` 复制为 `_local_artifacts/environment/model.env`，在本机填写供应商 HTTPS 地址、模型名和 API Key，不发到聊天或提交 Git。检查会把未填写、未真实调用标为 PENDING，不会用假响应冒充云端可用。真实调用可能产生供应商费用，首次只用合成文本。

## 9. Windows 安全弹窗

本机智能应用控制曾拦截 scikit-learn 1.9.1 的未签名扩展，导致 Sentence Transformers 无法导入。事件 3077 与安装文件定位相符；文件哈希与包记录一致，但不能据此取消系统安全判断。处理原则是核验官方发行包和兼容版本，不关闭防护、不加整目录排除、不改名或自签名绕过。

## 10. 接下来怎样学习业务

环境验收后，每课只推进一个可验证的业务节点：先讲职责和输入输出 → 画数据流 → 一起实现 → 写正常/失败/越权测试 → 查看数据库和日志变化 → Git 提交。第一课从 M04 商品领域和查询边界开始，不先把完整业务代码替你一次性生成。
