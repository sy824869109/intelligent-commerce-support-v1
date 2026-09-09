# M01 基础镜像安全修补与兼容验证（2026-09-09）

状态：DONE。本机安全扫描、隔离兼容、新平台切换复检及最终配置提交远端 CI 均通过。本文是本次维护记录，不替代历史 M01 验收，不宣称企业生产安全认证。

## 范围与版本

用户授权插入 M01 安全维护，暂停推进 M02.3。保持 MySQL 8.4.11、Redis 8.8.2、etcd 3.6.14、SeaweedFS 4.45、Milvus 2.6.23 的产品版本与业务架构；不修改原 KF、旧项目、参考压缩包，不迁移 Docker 数据。

| 镜像 | 本轮变化 | 准入要求 |
|---|---|---|
| etcd `3.6.14-ics.2` | gRPC-Go 1.83.1 → 1.83.2 | 三个 Go 程序均验证依赖，完整扫描 |
| Milvus `2.6.23-ics.2` | gRPC-Go 1.83.1 → 1.83.2 | 主程序和 planparser 共享库均验证依赖，完整扫描 |
| SeaweedFS `4.45-m01-security.2` | gRPC-Go 开发版本 → 已修复的同线固定提交 | 编译、完整扫描、S3/Milvus 契约回归 |
| MySQL、Redis | 不修改配方 | 使用当前漏洞库复扫原锁定镜像 |

SeaweedFS 精确依赖为 `v1.85.0-dev.0.20260825072537-93e31b48545e`，不是稳定正式版；选择原因和风险见 [ADR-0008](../decisions/ADR-0008-m01-grpc-security-maintenance.md)。其最小版本选择连带升级 13 个模块，包括 OpenTelemetry 1.44 → 1.45、otelhttp 0.69 → 0.70、Envoy 1.37 → 1.39。完整差异记录在模块锁和 `dependencies.patch` 中，不能描述成只改一个版本号。

## 写入与下载位置

- 项目根：`F:\heima\ai\python\project\i`。
- 配方与依赖锁：`deploy/images/{etcd,milvus,seaweedfs}/`；不改上游业务源码。
- 新增工具：`scripts/maintenance_evidence.py`、`scripts/maintenance_testbed.py`；新增负向测试：`tests/unit/test_maintenance_testbed.py`。
- 本轮主机证据：`_local_artifacts/m01-security-20260909/`。每次扫描独立保存 `image.tar`、`trivy.json`、`scanner.log`、成功时的 `evidence.json` 和服务级 `*-passed.json`。
- Go 模块与构建缓存：项目 `_local_artifacts/go-mod-cache`、`go-build-cache`；工具链复用项目 Go 1.27.1，不自动安装新工具链。
- Docker 构建使用已有 Docker 引擎、镜像库和 BuildKit 缓存所在地，不搬迁、不清理旧镜像或数据卷。构建会下载缺失的固定源码、Go 模块和上游 C++ 构建依赖；Milvus 上游部分 C++ 依赖通过分支获取，不能宣称全部传递输入均不可变。
- 扫描器复用固定 digest 的 Trivy 0.74.0；漏洞库下载到扫描容器的临时内存文件系统，不写主机 C 盘。
- 兼容测试复用既有 Conda 环境的 boto3 1.43.89 / pymilvus 2.5.18，不往 M02 平台运行环境追加 SDK，不改全局 PATH。

## 验证方法和防护

1. 构建新 `.2` 标签，保留 `.1` 及原数据；不以标签替换冒充运行升级。
2. 导出准确镜像 ID，校验归档与扫描报告关联；扫描全部严重级别，HIGH/CRITICAL 必须为 0，不启用忽略文件，不跳过无修复漏洞。中低危和 UNKNOWN 保留，零高危不等于无风险。
3. 验证实际 Go 制品中的修补版本，不只查看 `go.mod`。绑定镜像、报告、配方 SHA-256；证据有效期 24 小时，拒绝内容变化、越界路径和未来时间。
4. 五份扫描全部通过后才能生成隔离测试目录 `compatibility-lab`。新命名空间 `ics-v1-maint-20260909`，四个宿主端口仅绑定 loopback：33306、36379、38333、39530。
5. 隔离环境生成独立随机密钥与专用卷，不复制真实凭据、订单、知识库或 KF 数据。先以旧镜像写入合成哨兵，再使用同一批测试卷切换候选；验证 SQL/Redis/etcd、S3 读写、鉴权拒绝、向量写入和检索、跨重建与重启持久化。
6. 测试辅助脚本为现有受控入口的快照，只替换隔离命名空间和辅助镜像；保留卷归属、端口和密钥校验，并验证快照哈希。拒绝覆盖已有实验环境或自动重置失败数据。
7. 结束时停止本轮隔离容器，保留其合成卷与证据，不删除业务数据。通过后才能另行更新实际平台镜像锁；未通过不标记 M01 修补完成。

## 当前实测记录

- etcd 候选复扫：HIGH 0、CRITICAL 0、MEDIUM 1、UNKNOWN 6；三个 Go 程序均确认修补版本。
- Milvus 候选复扫：HIGH 0、CRITICAL 0、MEDIUM 60、LOW 29、UNKNOWN 6；主程序和 planparser 共享库均确认修补版本。中低危和未知项未隐藏，不等于全部风险已消除。
- MySQL 复扫：HIGH 0、CRITICAL 0、MEDIUM 7、UNKNOWN 1；原始报告在本轮证据目录。
- Redis 复扫：五个严重级别计数均为 0。
- SeaweedFS 首次本地重试因两个锁定模块下载 `unexpected EOF` 失败；再次构建通过模块校验和静态编译，最终复扫 HIGH 0、CRITICAL 0、MEDIUM 0、LOW 0、UNKNOWN 1。未跳过 Go 校验，未更换源。
- 本地 Foundation 最终 222 项测试，Windows 跳过 5 项符号链接测试，其余通过，包含维护工具 10 项专测。Ruff 和静态配置检查通过。
- 实现提交 `9785f6c` 已推送；[GitHub CI 34330902892](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34330902892) 为 SUCCESS，双平台基础/后端、Python 安全、四类镜像构建和漏洞门禁通过。Milvus 完整构建作业按既有策略 skipped，本轮用本机完整扫描补充，不把 skipped 写成远端通过。
- 恢复本轮工作时，旧平台、KF 及其他项目容器曾同时显示停止状态；未查明原因，不将退出 137 直接认定为 OOM。本次未发出停止、重启 KF/其他项目或迁移 Docker 的命令。之后观察到部分无关服务自行恢复，不进行干预。
- 隔离演练 `compatibility-passed.json` 于 2026-09-09 17:12（本地时间）记录 PASS：旧镜像写入、同卷强制重建升级、五服务数据保留、再次 stop/start 保留均通过；三个阶段各执行 45 项 S3/Milvus 契约检查。测试结束正常停止，仅保留合成卷和日志。
- 正式 `deploy/compose/images.lock.json`、`infra.compose.yml` 和卷权限初始化辅助镜像已切换为已验证 `.2` digest。SeaweedFS 构建工具 tag 同步为 `.2`，避免后续构建覆盖旧 `.1`。
- 仅恢复新平台 `ics-v1-dev` 五服务，复用原卷与凭据；实际运行 etcd/Milvus/SeaweedFS 均为修补镜像，五服务 healthy，45 项存储契约再通过。原 KF 和其他项目未操作。
- M02 回归：46 项后端测试、8 项真实 MySQL 集成测试通过；原开发数据库 `database_local.py status` 返回 READY。后端有 2 项既有测试依赖弃用警告，本轮不扩展升级依赖。临时 MySQL 集成容器及其合成 tmpfs 数据按工具归属校验后删除，不能恢复；真实平台卷未删除。
- 最终配置和补充防护提交 `80f436f` 已推送；[GitHub CI 34334369003](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34334369003) SUCCESS。全部已实施必需作业通过；未实施前端/运行时契约和手动 Milvus 作业仍按策略 skipped。本轮本机完整 Milvus 证据独立保留。
- M01 维护收口，M02.2 镜像阻塞解除；本轮不启动 M02.3。API 网关回环探测未连接成功，目前未启动；这不等于完整应用已上线。本轮启动范围仅 M01 五项基础服务。

## 当前固定镜像与回退边界

| 服务 | `.2` 镜像 digest |
|---|---|
| etcd | `sha256:de0b5e07f492b6ceb15b51ef14593142ce43ac66b0ad5c7973a3d7660f32ca3d` |
| SeaweedFS | `sha256:2ef7d372b429429c99116975d6ecfe789736d95ba43c00b7775b9510202273ba` |
| Milvus | `sha256:433dae6cd83235e5e412dc7f7c62090f72e132e429bd2e5983dff704ff5e7e47` |

原 `.1` 镜像、Git 历史及平台数据卷保留。未演练反向降级，不把“旧镜像还在”当作安全无损回退保证；需回退时先停写并评估数据格式兼容性，旧镜像亦有已知安全风险。本次只验证合成数据的正向升级和当前平台读写，不代表灾难恢复或全部业务验收完成。

源码锁中的 `BUILD_AND_SCAN_PENDING` 表示制作候选时的状态；最终验收以独立扫描、兼容报告和任务台账为准，不能仅凭该字段或镜像存在判断安全。
