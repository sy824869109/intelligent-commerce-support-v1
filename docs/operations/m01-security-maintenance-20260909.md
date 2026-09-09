# M01 基础镜像安全修补与兼容验证（2026-09-09）

状态：IN_PROGRESS。本文是本次维护记录，不替代历史 M01 验收，不代表候选已准入运行。

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

- etcd、Milvus 候选标签已存在；正在对最终镜像归档复扫。
- MySQL 复扫：HIGH 0、CRITICAL 0、MEDIUM 7、UNKNOWN 1；原始报告在本轮证据目录。
- SeaweedFS 尚在模块下载/构建；Redis 复扫进行中。
- 本地 Foundation：220 项测试，Windows 跳过 5 项符号链接测试，其余通过；Ruff、结构、治理与 Compose 静态校验通过。这些结果不是运行兼容性通过。
- 恢复本轮工作时，旧平台、KF 及其他项目容器曾同时显示停止状态；未查明原因，不将退出 137 直接认定为 OOM。本次未发出停止、重启 KF/其他项目或迁移 Docker 的命令。之后观察到部分无关服务自行恢复，不进行干预。
- 正式 `deploy/compose/images.lock.json` 和 `infra.compose.yml` 尚未切换；真实兼容测试尚未执行。M02.2 仍保留阻塞标记。

源码锁中的 `BUILD_AND_SCAN_PENDING` 表示制作候选时的状态；最终验收以独立扫描、兼容报告和任务台账为准，不能仅凭该字段或镜像存在判断安全。
