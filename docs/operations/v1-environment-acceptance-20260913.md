# V1 开发环境验收与行为说明

2026 年 9 月 13 日。本文交接本机开发环境，说明技术职责、实际改动、下载与文件位置、验证结果及使用方法。项目根目录为 `F:\heima\ai\python\project\i`，下文相对路径均从这里开始。

## 1 验收结论

本机开发所需的 Python、Vue 3、五项存储服务、本地模型、文件解析、百炼调用以及六项入口与监控服务已完成运行验收，可以进入 M04 的商品领域教学与实现。业务代码仍按模块逐步搭建，不把完整电商平台一次性生成。Git 提交和远端 CI 状态以任务台账及 Actions 为准。

这不是生产或局域网发布验收。业务前端页面、正式 RAG 在线接口、全部业务埋点、上传安全扫描业务、Golden Set、93 条跨模块用例及灾备演练尚未完成。Agent 和知识图谱不在 V1 本轮环境范围。

## 2 开发环境怎样协作

PyCharm 负责编辑、断点和启动；已有 V1 Conda 提供唯一业务 Python；项目内 Node 工具链负责 Vue；Docker 运行长期驻留的数据与监控服务。它们分工不同，不应把 Docker 数据放进 Conda，也不必为每个业务模块新建解释器。

| 层次 | 当前组合 | 作用与原理 |
|---|---|---|
| 后端运行 | Python 3.12.14；FastAPI、Uvicorn、Pydantic | 验证输入、运行 HTTP 服务和异步请求；版本细目在统一依赖锁 |
| 数据访问 | SQLAlchemy、Alembic、PyMySQL | 事务读写、可追溯表结构迁移、MySQL 协议连接 |
| 数据服务 | MySQL 8.4.11；Redis 8.8.2 | MySQL 保存业务事实；Redis 提供短期状态、缓存和队列基础 |
| 知识存储 | Milvus 2.6.23；etcd 3.6.14；SeaweedFS 4.45 | 向量索引、元数据、S3 对象存储；不是三份相同数据库 |
| 检索开发 | LangChain 1.3.9；Core 1.4.6 | 封装检索与模型接口，保留 KF 核心检索分层 |
| 本地模型 | BGE-M3；BGE-reranker-v2-m3；torch 2.13.0 CPU | 文本转 1024 维向量；对问题和候选段落联合评分 |
| 模型与解析库 | Transformers 5.10.1；Sentence Transformers 6.0.1；Docling 2.106.0；pypdf 6.16.1 | 本地模型加载；提取 PDF 文本、表格和中文扫描内容 |
| 云端生成 | 百炼 OpenAI 兼容接口；qwen-plus | 接收提示词并生成文本；供应商模型别名不是不可变权重版本 |
| 前端开发 | Node 24.20.0；pnpm 10.34.5；Vue 3.5.42；TypeScript 6.0.3；Vite 8.2.2 | 包管理、类型检查、组件编译和开发服务 |
| 前端配套 | Pinia 3.0.4；Router 4.6.4；Element Plus 2.14.5；Axios 1.20.0 | 页面状态、路由、组件和 HTTP 调用 |
| 测试 | pytest；Vitest 4.1.11；Playwright 1.62.1；Ruff；Bandit；pip-audit | 单测、真实浏览器、格式与静态安全、已知依赖漏洞检查 |

完整 Python 和前端传递依赖分别以 `deploy/dev-environment/v1-requirements.lock` 与 `deploy/dev-environment/frontend/pnpm-lock.yaml` 为准。顶层服务选较新稳定或维护分支，不盲目追新。上游传递依赖可能使用 Go 伪版本，仍需精确审查。

## 3 实际数据链路

入口验收链路是：本机 HTTPS 请求 → Nginx 28443 → 临时 FastAPI 网关 28000 → MySQL 就绪检查 → 返回结果；认证接口在匿名请求下返回 401。该过程验证证书、代理、数据库和关联日志，测试结束停止本次拥有的网关进程。

检索验收链路是：合成问题与两段合成文档 → 本地 BGE-M3 → 1024 维向量 → LangChain Milvus 适配器 → 稠密与 BM25 混合召回；重排模型独立验证相关段落分数更高。唯一命名的测试集合用完删除。百炼用单独的少量合成文本验证，不发送客户文档。这些组件探针不是完整线上 RAG 闭环。

监控验收链路是：合成 OTLP HTTP 信号 → Nginx 24318 → Collector → 指标进入 Prometheus、追踪进入 Tempo、日志进入 Loki → 逐项查询回读。Grafana 经内部网络读取这三个数据源，不持有业务主数据。gRPC 24317 补测三个空 Export 请求，只证明协议与服务分派，未冒充真实数据持久化测试。

五个监控后端位于 internal 网络。本机诊断端口统一由连接 edge 和 internal 网络的 Nginx 绑定，解决 Docker Desktop 对仅内部网络不发布端口的问题。未扩大为局域网管理入口。Python OTel SDK 自动插桩尚未安装或接入；已有网关使用 M02 的观测基础库，后续业务接入需单独测试。

## 4 本轮安全修补做了什么

没有把扫描失败直接忽略。先保留官方候选和失败证据，再固定官方源码提交、修补受影响依赖、构建新平台专用镜像，最后扫描实际制品并联测。Go 1.27.1 仅作为本地构建工具，不改变业务语言。原 KF 源码、环境、压缩包和原电商项目未修改。

| 派生镜像 | 主要处理 | 最终 HIGH CRITICAL |
|---|---|---|
| ics-nginx 1.30.4-env.1 | libuuid 升为 2.42.3-r1；补齐只读根目录下的临时路径 | 原始 0 |
| ics-prometheus 3.13.3-env.1 | 使用 3.13 LTS；gRPC 1.83.2、x/crypto 0.55；保留官方运行布局 | 原始 0 |
| ics-otelcol 0.160.0-env.1 | 官方 OCB 定制分发，只包含实际配置组件 | 原始 0 |
| ics-tempo 3.0.3-env.1 | gRPC 1.83.2、x/crypto 0.55、thrift 0.24；配置可写 live_store 路径 | 原始 0 |
| ics-loki 3.7.7-env.1 | 修补 gRPC 1.83.2 并重建；保留官方运行布局 | 原始 0 |
| ics-grafana 12.4.10-env.1 | gRPC 1.83.2、thrift 0.24；OpenSSL 3.5.8-r0；保留 UI 与插件 | 原始 2；复核 2；未解决 0 |

Grafana 使用上游支持的纯 Go SQLite 构建路径，实际启动、数据库迁移及数据源健康检查通过；并非用空实现代替数据库。Collector 不是完整 contrib 组件全集，仅包括 OTLP 接收、内存限制、批处理、所需导出器、健康检查和配置读取组件。

经用户明确同意，只有 CVE-2026-21728 和 CVE-2026-28377 两项可适用确切证据复核。实际依赖为 `github.com/grafana/tempo` 的 `v1.5.1-0.20260427112133-525d1bab07e0`，其源码包含两个官方修复提交。判定绑定镜像 ID、配置 ID、Grafana 二进制 SHA-256、扫描目标和精确依赖版本；Go 模块校验和与上游修复信息保存在复核文件。

规则位置为 `deploy/dev-environment/security/grafana-reviewed-fixes.json`。启动时重读原始报告并复算哈希，任何身份变化或其他高危/严重告警仍阻断。完整结果是 PASS_REVIEWED，不是“原始零漏洞”。扫描仍受当时漏洞库覆盖限制；保留了 Alpine 生命周期资料及一条漏洞详情不完整的警告，不能据此承诺不存在未知风险。

## 5 下载与文件位置

已有解释器仍为 `F:\heima\ai\python\day01\Anaconda\envs\intelligent-commerce-support-v1\python.exe`。Python 包装在此环境，是用户指定的项目内存放原则例外。未创建新 Conda，未迁移现有 Docker 数据，未更改 GPU 驱动、全局 PATH、防火墙或系统证书信任库。

| 相对位置 | 存放内容 | GitHub |
|---|---|---|
| deploy/dev-environment | Python、模型、镜像锁和前端夹具；非秘密配置 | 上传 |
| deploy/dev-environment/security | 六个 Dockerfile、Collector 组件清单、两项确切复核规则 | 上传 |
| scripts | 准备、构建、扫描、启动、模型和跨服务探针 | 上传 |
| tests/unit | 源码安全解包及定向告警复核测试 | 上传 |
| docs/operations 与 docs/decisions | 本说明、使用指南、选型决策；进度另在 docs/progress | 上传 |
| _local_artifacts/dependencies | Node 解压运行时、pnpm；历史解释器目录保留 | 不上传 |
| _local_artifacts/models | 固定 revision 与 SHA 的 BGE、解析和 OCR 模型资产 | 不上传 |
| _local_artifacts/caches | pip、uv、pnpm、浏览器、模型下载和工具缓存 | 不上传 |
| _local_artifacts/environment/security-build | 官方源码归档、解包目录、编译产物与 build.json | 不上传 |
| _local_artifacts/environment/image-audit | 原始和候选扫描、最终 summary、历史失败报告 | 不上传 |
| _local_artifacts/environment/telemetry-data | Grafana、Prometheus、Tempo、Loki 等新增监控持久化数据 | 不上传 |
| _local_artifacts/environment/secrets | 本地证书、私钥和 Grafana 密码 | 不上传 |
| _local_artifacts/environment/model.env | 百炼地址、模型和密钥 | 不上传 |
| _local_artifacts/environment/deliverables | 本次 Word 交付文件 | 不上传 |

Node 压缩包留在 environment 下并核验官方 SHA；BGE 文件以模型锁追溯来源，原 KF 中与官方哈希匹配的文件仅只读复制，其余按固定源获取。Docling 的 PDF、表格、OCR 资产支持离线探针。先前 Windows 安全控制曾拦截 scikit-learn 1.9.1，当前使用核验后的 1.9.0，未关闭防护或添加整目录排除。

本轮新下载四套固定提交源码：Prometheus b273ae3adeb6、Grafana 81407c71e96e、Tempo 1900ed7bb5ca、Loki 7a40404f32b3；完整提交、归档和制品哈希在各 build.json。官方 OCB 0.160.0 Windows 构建器在 security-build/collector-0.160.0/ocb.exe，其 SHA-256 为 `2a40f86342f25bf0ac27bcbbc6da4054b0acd1541fd7d69a02f6c6aabac535f1`。Go 下载的模块源代码留在 `_local_artifacts/go-mod-cache`，工具链在 `_local_artifacts/toolchains`。

源码解包拒绝路径越界、重复和特殊文件，Windows 使用长路径形式；源码链接跳过并记录，不偷偷跟随到其他目录。网络中断时重试，未关闭 TLS 或 Go 校验数据库。官方基础镜像由 Docker 下载；其存储继续使用 Docker 原有位置，未为满足 F 盘约束迁移旧数据。

## 6 删除与保留记录

编译期间 F 盘约剩 15.7 GiB，Loki 因磁盘使用率阈值拒绝写入。确认无 Go 编译进程、目标是项目内非链接目录后，仅清理 `_local_artifacts/go-build-cache` 的可再生编译缓存，释放约 10.6 GB，盘余约 26.3 GiB。缓存可重新编译生成；源码、下载模块、模型、镜像和数据库均保留。

扫描器仅删除它本轮新导出的临时镜像 tar；Docker 镜像和扫描 JSON 保留，可重新导出。旧失败扫描移入 image-audit/before-derived-20260913，旧 Nginx 归档改名保留。模型测试只清理其唯一命名的合成集合；未执行 Docker 全局清理、卷删除或业务数据删除。

## 7 验收记录与局限

| 检查 | 结果 | 证据与解释 |
|---|---|---|
| 解释器及包一致性 | PASS | check-all.json；V1 Python 3.12.14；真实导入和 pip check |
| 本地模型和混合检索 | PASS | check-all.json；1024 维与合成排序；集合清理 |
| PDF 表格 中文 OCR | PASS | check-all.json；离线合成文档，不代表所有真实文件 |
| 百炼 | PASS | HTTP 200；少量合成提示词；不重复调用充当稳定性压测 |
| 六镜像准入 | PASS_REVIEWED | image-audit/summary.json；原始 2 项，未解决 0 项 |
| HTTP 三信号写入查询 | PASS | check-all.json；追踪 c37b0477aac441de8ff96cf6cad25be1 |
| gRPC 和 Grafana | PASS | check-telemetry-access.json；空 Export；三数据源；匿名 401 |
| TLS 网关 数据库 | PASS | check-gateway-tls.json；确切 CA；关联日志；临时进程已停 |
| Python 依赖安全 | PASS | python-audit-complete.json；含 torch CPU 对应公开版本核对 |
| Vue 与真实浏览器 | PASS | 前端工具链夹具通过；不是用户端、客服端页面验收 |
| 已实现业务基础回归 | PASS | 后端 90、契约 169、真实 MySQL 12 项 |
| 基础治理与单测 | PASS | 244 项运行，Windows 跳过 5 个受权限限制的用例 |

报告位于 `_local_artifacts/environment`；软件锁是静态规格，运行报告是某次实际结果，两者不能混淆。安全构建中的 build.json 仍记录“当时尚未扫描”，后续最终准入以 image-audit/summary.json 为准，保留阶段记录不回填历史。

本地探针会在内存中去掉百炼密钥前误带的界面标签，不修改私密文件。后续业务模型配置读取必须统一处理，不可直接照抄未规范化字段。已在聊天出现的密钥应在上线前轮换；文档、日志和 Git 均不记密钥。尚未创建电商平台默认管理员，首次管理员按 M03 指南本机交互初始化。

## 8 日常启动与重建

在 PyCharm 打开项目根目录，选择已有 V1 解释器。先在 PowerShell 执行 `. .\scripts\enter_environment.ps1`，使当前终端使用正确运行时和 F 盘缓存。已有服务日常执行：

```powershell
python scripts/local_infra.py up
python scripts/environment_services.py up
python scripts/environment_services.py health
python scripts/run_gateway.py --with-database
```

最后一条前台运行，Ctrl+C 正常退出。访问 `https://localhost:28443/environment/health` 查看入口；Grafana 在 `http://127.0.0.1:23000`，管理员名 admin，密码只在本地 secrets/grafana_password。自签名证书未加入 Windows 信任，浏览器可能提示不受信任；探针使用确切 CA，不用关闭验证绕过。

环境复验可运行 `python scripts/check_environment.py runtime`、`python scripts/check_environment.py telemetry`、`python scripts/check_telemetry_access.py`。云端真实调用需显式 `python scripts/check_environment.py cloud --live-cloud`，可能产生费用。扫描超过 3 天时启动会要求先运行 `python scripts/scan_environment_images.py`。

新机器复现不是仅执行一个 pip 命令：先准备已有 V1、Docker 和受信工具，运行 setup_v1_environment.ps1 -IncludeFrontend；按模型锁准备文件；按 security Dockerfile 和固定源码构建六镜像，再 capture-images、扫描、prepare 和 up。精确复核不会自动授权新镜像身份，重建后必须重新核验两项证据。不能将本机镜像 ID 当作可从公共仓库直接拉取的地址。

## 9 接下来怎样搭建业务

先做 M04.1 商品模型与查询边界：讲清商品、SKU、库存的职责与租户归属，画出请求到数据库的数据流，再实现迁移、查询、正常与越权测试。每次结束说明输入输出、写入哪些表、怎样在 PyCharm 调试，以及本批 Git 提交。之后逐模块推进业务；KF 核心 RAG、Agent、知识图谱仍遵循既定阶段边界。

## 10 官方依据与本地追溯

- Prometheus LTS：https://prometheus.io/docs/introduction/release-cycle/
- Grafana 维护：https://grafana.com/docs/grafana/latest/upgrade-guide/when-to-upgrade/
- Collector 定制构建：https://opentelemetry.io/docs/collector/extend/ocb/
- 第一项修复：https://grafana.com/security/security-advisories/cve-2026-21728/ 与 https://github.com/grafana/tempo/pull/6525
- 第二项修复：https://grafana.com/security/security-advisories/cve-2026-28377/ 与 https://github.com/grafana/tempo/pull/6711

具体镜像 ID 和配方 SHA 在 deploy/dev-environment/images.lock.json；实际二进制、报告 SHA 与复核数量在最终扫描 summary；变更源码范围与提交记录由 Git 跟踪。以上来源支持版本与修复判断，不替代本机实测，也不构成企业生产可用性认证。
