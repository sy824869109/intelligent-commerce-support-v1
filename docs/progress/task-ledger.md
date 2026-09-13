# 项目任务台账

## 状态定义

- `TODO`：尚未开始。
- `IN_PROGRESS`：正在实施或尚未通过全部交付门禁。
- `BLOCKED`：存在无法在当前权限或环境内解决的阻塞。
- `DONE`：实现、测试、文档、提交和 GitHub 推送全部完成。

## 当前任务

**ENV-V1 集中环境准备 IN_PROGRESS（2026-09-13）**：根据用户新要求，环境集中搭建、业务逐步教学；统一已有 `intelligent-commerce-support-v1` Conda，Vue 3，本地向量/重排 + 百炼云端 LLM。已通过 90 项后端、169 项契约、12 项 MySQL 回归与前端工具链测试，模型下载、监控、安全审计及云端配置仍在验收，不标为整体完成。见 [环境说明](../operations/v1-environment-guide.md)。

**M03.1–M03.4 全部 DONE（2026-09-10）。** 最终实现 `3c8512d`，CI `34459754847` SUCCESS；90 项后端、169 项契约、12 项真实 MySQL 与基础检查通过。开发库已迁移到 m03_0003，真实启动及匿名 401 验证通过，临时进程已停止。无默认管理员或演示账号，首次使用需本机交互初始化密码。见 [M03 完整行为与验收](../operations/m03-identity-acceptance.md)。下一阶段 M04 尚未开始；以下为历史过程状态。

M03.1–M03.4 实现与本地功能测试完成，IN_PROGRESS 待最终签收：身份模型、真实认证端点、刷新重放吊销、管理员/客服组管理、当前权限与资源归属依赖；第一轮 87 项后端、169 项契约、12 项真实 MySQL 通过。完整行为、网络审计限制及初始化说明见 [M03 验收](../operations/m03-identity-acceptance.md)。不植入默认管理员密码。

**M02.1–M02.4 全部 DONE（2026-09-10）。** 最终实现 `c98ae47`、修正 `aaa8058` 已推送，CI `34454383386` SUCCESS。63 项后端、169 项契约、9 项真实 MySQL 与基础检查通过，开发库审计迁移 READY，实际网关联测通过且临时进程已停止。完整行为、失败修正和边界见 [M02 最终验收](../operations/m02-final-acceptance.md)。下一阶段 M03 尚未开始。下方待验收/IN_PROGRESS 为历史过程记录。

M02 最终批本地完成，远端待验证：63 项后端、169 项契约、9 项真实 MySQL、224 项基础测试运行成功（Windows 跳过 5 项）；开发库审计迁移 READY，真实 HTTP/数据库/trace/日志联测通过。M02.4 在 CI 签收前保持 IN_PROGRESS，见 [总验收与行为记录](../operations/m02-final-acceptance.md)。上一批 `6b44191` 的 CI `34448572288` SUCCESS。

M02.4 第一批 IN_PROGRESS：观测共享函数（上下文隔离、白名单 JSON、固定指标桶、审计记录校验），本地 56 项后端与 169 项契约通过，远端待验证。尚未接入网关或持久化审计，见 [实施记录](../operations/m02-4-observability-foundation.md)。

M02.3 合同阶段 DONE：第六批实现 `694b5f4` 已推送，CI `34447200294` SUCCESS；169 项契约、46 项当批后端及基础检查通过。包含原 18 项业务设计、六项媒体扩展、平台事件和兼容基线；运行端点、认证、上传扫描及业务闭环不属于此次合同完成。以下 IN_PROGRESS/待验证描述为各批历史状态。

M02.3 第六批：新增六项独立媒体设计端口，保留原合同及其摘要基线；进入收口验证，整体仍 IN_PROGRESS，见 [媒体端口与复核](../api/m02-3-media-ports.md)。上一批实现 `904f6aa` 的 CI `34446320974` 已确认 SUCCESS；下面第五批“待验证”为历史记录。

M02.3 第五批本地通过：消息内容/来源、游标范围与过期、上传许可及 READY 条件、固定响应 fixtures、独立兼容基线；150 项契约、46 项后端通过，224 项基础测试运行成功（Windows 跳过 5 项）。远端验证待本次提交。上传/来源/附件读取路径及富媒体消费合同仍待最终冻结，M02.3 整体 IN_PROGRESS，详见 [第五批说明](../api/m02-3-handoff-compatibility.md)。

M02.3 第四批已验收：公开响应白名单、业务请求/响应模型、18 项独立设计路径、HTTP 状态与错误映射校验；120 项契约、46 项后端测试及 224 项基础检查通过（Windows 跳过 5 项）。实现 `c178fb8` 已推送，CI `34434163649` SUCCESS。实际网关路径未增加，M02.3 整体仍 IN_PROGRESS，详见 [第四批说明](../api/m02-3-public-api-design.md)。

M02.3 第三批已验收：售后申请/页面聊天提交、服务端预检绑定、精确金额、分页与命令结果 DTO；83 项契约、46 项后端测试及 224 项基础检查通过（Windows 跳过 5 项）。实现 `8ddd156` 已推送，CI `34432601691` SUCCESS。M02.3 整体仍 IN_PROGRESS，仅合同纯函数、无交易接口，见 [第三批说明](../api/m02-3-confirmation-dtos.md)。

M02.3 第二批已验收：领域信封复用、公开回复载荷读取、18 项操作/13 类错误目录；49 项契约、46 项后端测试及 224 项基础检查通过（Windows 跳过 5 项）。实现 `642acf1` 已推送，GitHub CI `34430866686` SUCCESS。未新增业务端点，M02.3 整体仍 IN_PROGRESS，详见 [第二批说明](../api/m02-3-domain-policies.md)。

M02.3：IN_PROGRESS。第一批已验收：现有 OpenAPI、八类事件机器合同、SSE 编码与真实契约 CI；本地 31 项契约、46 项后端测试与 224 项基础检查通过（Windows 跳过 5 项）。实现 `eafd033` 已推送，GitHub CI `34429732803` SUCCESS（含双平台契约）。后续业务/领域合同未完成，见 [合同说明](../api/m02-3-contract-foundation.md)。

| 任务 | 状态 | 本地交付 | GitHub |
|---|---|---|---|
| M00.1 开发基线初始化 | DONE | 启动包校验、标准文档、资产台账、独立 Conda 环境、Git 仓库与本地原子提交 | 已推送 `origin/codex/v1-greenfield`；基线提交 `591d1a4` |
| M00.2 项目目录骨架 | DONE | 应用、共享包、部署、文档、测试目录，环境模板、边界文档和结构检查 | 已推送 `origin/codex/v1-greenfield`；实现提交 `367debb` |
| M00.3 项目治理规则 | DONE | ADR、变更日志、版本策略、完成定义、安全与 PR 规则及自动治理检查 | 已推送 `origin/codex/v1-greenfield`；实现提交 `37004a4` |
| M00.4 GitHub CI 骨架 | DONE | 双平台工作流、哈希锁定工具、配置/资产守卫、34 个基础测试及文档通过 | 实现 9842543；Windows 修正 1193aa2；[运行 34011335143 成功](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34011335143) |
| M01.1 本地基础设施 Compose | DONE | 五服务 Compose、固定安全镜像、loopback/内部网络边界与真实闭环通过 | M01 最终提交与 CI 见下方收口记录 |
| M01.2 初始化与持久化 | DONE | 两个固定 S3 桶、非 root 卷准备、五类哨兵 stop/start 持久化与精准清理通过 | M01 最终提交与 CI 见下方收口记录 |
| M01.3 环境配置分层 | DONE | dev/test/prod 无密钥配置，开发仅 loopback，生产 TLS/外部密钥契约 | M01 最终提交与 CI 见下方收口记录 |
| M01.4 生命周期与升级演练 | DONE | 统一启动/健康/停止/重启测试/强制重建入口，五类数据跨重建保留 | M01 最终提交与 CI 见下方收口记录 |
| M02.1 后端应用骨架 | DONE | 应用工厂、健康/错误/关联日志、24 项后端测试、Bandit/pip-audit、本机 HTTP 通过 | acc5fb3；GitHub Actions 34187050206 双平台后端与安全门禁 SUCCESS |
| M02.2 数据库事务与事件基础 | DONE | SQLAlchemy、Alembic、Outbox/Inbox；最终回归含审计扩展，9 项真实 MySQL 通过，开发库 READY | 原实现 5f28bbc；最终 CI 34454383386 SUCCESS；测试网关已停止 |
| M02.3 共享接口与流式合同 | DONE | 169 项契约、8 类平台事件、18 项业务设计与6项媒体扩展、独立兼容基线 | 694b5f4；最终回归 CI 34454383386 SUCCESS |
| M02.4 观测与审计基础库 | DONE | 网关 trace/日志/有界指标、事务审计、迁移及失败回滚、真实 HTTP 联测 | c98ae47、aaa8058；CI 34454383386 SUCCESS |
| M03.1 身份组织模型 | DONE | 12 张身份相关表、租户复合外键、3 类角色与权限种子；无默认账号 | 942fba7；最终 CI 34459754847 SUCCESS |
| M03.2 认证与会话 | DONE | 登录、刷新轮换/重放吊销、退出、改密吊销、密码策略和持久限流 | 942fba7、3c8512d；CI 34459754847 SUCCESS |
| M03.3 租户资源授权 | DONE | API 默认认证、RBAC 与领域资源 loader 授权、成员/客服组管理 | 5fa958a；CI 34459754847 SUCCESS |
| M03.4 权限矩阵 | DONE | 三角色订单/知识/工单矩阵及 HTTP/真实 MySQL 验证；总计 90 项后端、12 项 MySQL | 3c8512d；CI 34459754847 SUCCESS |
| M01 安全维护 20260909 | DONE | 五镜像复扫 HIGH/CRITICAL 为 0；隔离同卷升级/重启通过；新平台修补镜像五服务健康；222 项基础检查（Windows 跳过 5 项）、46 项后端、8 项 MySQL 回归通过 | 9785f6c、80f436f 已推送；CI 34330902892、34334369003 SUCCESS；见维护行为记录 |

M02.1 新环境在项目 `_local_artifacts/dependencies/platform`，后续缓存已固定到项目内；首次审计误生成的 C 盘缓存因迁移失败和清理被安全检查拦截而暂留，详见行为记录。既有 Docker 数据不迁移。
M02.2 原安全阻塞已于 M01 维护解除。M02.3 第一批合同开始实施，M02.4 尚未开始；历史阻断证据保留，不代表当前仍阻塞。
详见 [M02.1 行为记录](../operations/m02-1-implementation-log.md) 和 [验收](../testing/m02-1-gateway.md)。

## M01 最终收口（2026-09-07）

- 五个新平台容器均为 healthy；MySQL、Redis、etcd 认证读写及 S3/Milvus 45 项合成契约通过。
- stop/start 与 `--force-recreate` 两轮五类持久化哨兵验证通过并精准清理；未删除任何卷。
- 五个安全派生镜像完整归档扫描均为 0 HIGH/CRITICAL；配方、源锁和五路 GitHub 构建扫描已纳入仓库。
- 本地结构、治理、48 条标准引用、格式、静态检查和 203 项单测通过；Windows 跳过 5 个符号链接权限用例，由 Linux CI 覆盖。
- 三份只读参考归档 SHA-256 与基线完全一致，原 KF 六个容器均 healthy。详细清单见 [行为记录](../operations/m01-implementation-behavior-log-20260907.md) 与 [最终验收](../testing/m01-final-validation.md)。
- 93 条业务用例仍为 NOT_RUN；下一任务是 M02.2，不提前声称业务系统已建成。

## 补充文档交付

### M01.1 Milvus 自维护构建决策（2026-09-07）

- 用户确认采用 [ADR-0005](../decisions/ADR-0005-maintained-milvus-security-build.md)：以签名的 Milvus v2.6.23 为功能基线，自建并维护安全修补镜像。
- 当前只确认构建、扫描、兼容和退出策略；候选尚未生成或接入 Compose，M01.1 保持 IN_PROGRESS，M01.2–M01.4 仍未开始。

### M01.1 安全评估与验收工具增量（2026-09-07）

- 自维护构建已开始，尚未产出通过全部门禁的 Milvus 镜像。新增双制品扫描验收工具及 14 项离线测试，详见 [构建候选记录](../testing/m01-milvus-build-candidate.md)；原 KF 六个服务恢复后均健康，原源码/配置/数据未改。M01.1 保持 IN_PROGRESS，M01.2–M01.4 不提前推进。

- 镜像配方提交 `501766a` 已推送；[CI 34071349513 成功](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34071349513)，包含双平台基础检查及真实镜像构建扫描。
- 新增独立本地镜像证据入口，实际 build/verify 通过；44 个新增测试本机通过 39、权限原因跳过 5。完整证据与 Milvus 自维护发行包的决策边界见 [记录](../testing/m01-storage-image-security.md)。不修改现有三服务 Compose，不宣布 M01.2–M01.4 完成。

- 新增 [安全评估记录](../testing/m01-security-evaluation-20260907.md)、无 I/O 配置生成器、S3/Milvus 合成探针、SDK 哈希锁及 23 项探针单测；本地完整 CI 共 102 项通过。
- 原 SeaweedFS 4.45 实扫 2 HIGH/23 UNKNOWN；Milvus 2.5.27 实扫 3 CRITICAL/51 HIGH。未把隔离或版本较新当作修复，派生安全构建/维护版本继续核查。
- 本增量不复制未准入 Compose、不启动新知识存储，不推进 M01.2。实现 `1c9a861` 已推送；[双平台 CI 34047165219 成功](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34047165219)。
- 后续独立镜像增量：SeaweedFS 三项依赖修补及最小运行系统已构建，完整本地复扫为 0 HIGH/CRITICAL、1 UNKNOWN；见 [验证记录](../testing/m01-storage-image-security.md)。新增真实镜像构建/扫描 CI，但 S3/Milvus 运行和 M01.2–M01.4 仍未完成。

### M01.1 当前增量（2026-09-06）

- 用户确认先评估受维护 S3 替代，不授权启动旧 MinIO。见 [ADR-0004](../decisions/ADR-0004-object-storage-security-gate.md)。
- 只实施新 project MySQL/Redis/etcd，见 [运行说明](../../deploy/compose/README.md)。
- [验证证据](../testing/m01-1-infrastructure.md) 与 [替代评估](../operations/s3-alternative-evaluation.md) 随原子增量交付；SeaweedFS 是首选待测候选，不是已采用。
- M01.1 仍 IN_PROGRESS；下一增量仍在本任务内完成存储安全准入/兼容验证，不进入 M01.2，不把 93 条业务用例改为通过。
- 交付证据：`4774ce2bc24177ed542e240a58a7c6fbc9c5524c` 已推送 `origin/codex/v1-greenfield`；运行 `34027009809` 的 Windows/Linux Foundation 成功，未实现应用作业仍 skipped。14 个配置/测试/文档文件，无密钥、原项目或归档。三份 ZIP 哈希与基线一致。

- 2026-09-06 衔接修订：标准 1.1、48 条规则、93 条 NOT_RUN 业务用例、十四类范围映射，图 05 同步。结构/治理/标准检查通过；Chrome 验证 50 节点无溢出、无穿框，六区导航与缩放通过。复核详情见 [记录](v1-handoff-review-20260906.md)。

- 2026-09-06：[V1 四项实施标准](../implementation-standards/v1/README.md)，包含 44 条编号规则、80 条初始 NOT_RUN 验收用例及只读文档检查脚本。
- 验证范围：文档编号/引用/表格/JSON/链接、仓库结构与治理；不代表 80 条业务用例已执行。
- 本次不推进实施任务：M00.4 仍为 TODO，不修改参考项目或 KF 核心。相关提交随文档通过 Git 原子提交与远端同步追溯。

## M00.1 验收条件

衔接规则修订提交：`3c3ac0d`，已推送 `origin/codex/v1-greenfield`。不改变原始资产与 KF 核心。

- [x] 确认开发根目录。
- [x] 核验启动 TAR 的 SHA-256。
- [x] 仅提取架构、提示词、技术选型与资产规则文档。
- [x] 建立旧项目和 KF RAG 的只读台账。
- [x] 定位本地 Conda 与 PyCharm。
- [x] 创建并验证独立 Conda 环境。
- [x] 初始化 Git 仓库与开发分支。
- [x] 创建原子提交。
- [x] 推送 GitHub 并记录 Commit SHA。

## M00.2 验收条件

- [x] 建立三个前端和七个后端/Worker 应用目录。
- [x] 建立 contracts、domain、observability、testing 共享包目录。
- [x] 建立部署、架构、API、运维、测试和进度目录。
- [x] 建立 `.env.example`，且不包含真实密钥。
- [x] 建立许可证、运行时版本文件和根级开发命令。
- [x] 为所有一级模块写明职责、数据所有权和禁止事项。
- [x] 通过自动化结构检查和 Git 忽略检查。
- [x] 创建原子提交并推送 GitHub。

## M00.3 验收条件

- [x] 建立 ADR 模板、编号规则和状态流转规则。
- [x] 记录模块化单仓与 KF 知识服务边界的首份 ADR。
- [x] 建立产品、API、事件、迁移、Prompt、模型和知识版本策略。
- [x] 建立 CHANGELOG 和当前开发版本。
- [x] 建立任务、模块和 V1 发布三级 Definition of Done。
- [x] 建立贡献、分支、提交、安全报告和 PR 检查规则。
- [x] 通过治理文件、结构、敏感信息和 Git 差异检查。
- [x] 创建原子提交并推送 GitHub。

## 进度纪律

## M00.4 验收与远端证据

- [x] 按顺序完成衔接修订及图 05 复核，提交 `3c3ac0d` 已推送。
- [x] GitHub push/PR 触发与双平台真实 Foundation 作业，Action SHA/权限/超时受控。
- [x] 本地 Conda 运行 `python scripts/ci.py`，结构、治理、48 规则/93 用例引用、格式、静态、资产与 34 个基础测试通过。
- [x] 初次运行 `34011147030` 的 Windows Python 安装失败已记录，未标假通过；`1193aa2` 改用同版本 Conda，未降级基线。
- [x] 修正运行 `34011335143`：Linux success（14 秒）、Windows success（2 分 22 秒）；五个未实现应用/契约/安全审计/镜像 job 均 skipped。
- [x] 启动 TAR SHA-256 仍为 `7690AAD97C5593C3AA2791C48FD05096D723859AF75653A4A78BDEDABEB0C7AE`；参考项目及 KF 核心未改。
- [x] 实现及修正均已推送，ADR-0003 补记 Windows 运行时决策；运行证据与下一任务清楚。

本地仅增加 CI 专属 Ruff/PyYAML；没有启动 MySQL、Redis、MinIO、Milvus 或应用服务。34 个工具测试不是 93 条业务验收，后者仍 NOT_RUN。详见 [CI 说明](../testing/m00-4-ci.md)。

### 后续纪律

2026-09-06 连线图展示补充：新增 [图 14 全景流程与逐步讲解](../architecture/v1-review-20260905/V1全景技术流程图_逐步讲解.html)，在同一画布展示 68 节点、85 连线及 17 个讲解区域；提供 PNG/SVG、节点说明和可复现检查。PAGE/CHAT、人工、知识修订及正式发布衔接完成静态复核。仅文档展示变化，M01.1 未开始，业务验收仍 NOT_RUN，KF 与参考资产未动。

2026-09-06 文档展示补充：新增 [分层流程与示例](../architecture/v1-review-20260905/V1分层流程与示例.html)，包含图 06–13、69 个主节点和 [三条完整示例走读](../architecture/v1-review-20260905/V1分层流程_示例走读.md)。只提高流程层级、数据流向和异常出口的可审查性；标准 1.1、48 条规则和 93 条 NOT_RUN 用例不变，M01.1 尚未开始。图 05 和参考资产保留。

只有当前任务的所有验收项通过后才能开始下一任务。每次行为变化都必须同步更新代码注释、README、接口文档和本台账。
