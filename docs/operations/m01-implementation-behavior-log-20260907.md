# M01 实施行为全记录（2026-09-06—2026-09-07）

## 1. 结论与操作边界

本轮一次性完成并验证 M01.1–M01.4。所有运行资源属于新平台 `F:\heima\ai\python\project\i` 和 Compose project `ics-v1-dev`。没有编辑、覆盖、迁移或删除原智能客服、KF RAG、三个参考 ZIP 及其数据；没有执行 `down -v`、Docker 全局 prune、全局停止或镜像发布。

行为记录不包含任何密码、token、S3 key 或完整 Compose 展开结果。93 条业务验收仍为 NOT_RUN。

## 2. 写入项目仓库的内容

### M01.1：五服务基础设施与安全镜像

- 修改：`.github/ci-stages.json`、`.github/workflows/ci.yml`、`deploy/compose/.env.example`、`deploy/compose/images.lock.json`、`deploy/compose/infra.compose.yml`、`scripts/verify_ci.py`、`scripts/verify_infra.py`、`tests/unit/test_ci_image.py`、`tests/unit/test_infra.py`。
- 新增：`deploy/images/mysql/`、`redis/`、`etcd/`、`milvus/` 下的 Dockerfile、README 和源锁；Milvus 另含 `go.mod.lock`、`go.sum.lock`、`modules.sha256`。既有 `deploy/images/seaweedfs/` 保持为第五份审查配方。
- 结果：MySQL、Redis、etcd、SeaweedFS、Milvus 使用本地安全派生镜像，tag 与镜像 ID 双锁；GitHub 五路矩阵真实构建、导出并以固定 Trivy 镜像阻断 HIGH/CRITICAL。

### M01.2：初始化、真实探针与持久化

- 修改：`scripts/local_infra.py`、`scripts/storage_config.py`、`scripts/storage_probe.py`。
- 行为：兼容已有三服务本机凭据，额外初始化四份存储配置；创建固定 `ics-knowledge`、`ics-milvus` 桶；准备非 root etcd/SeaweedFS 卷；用随机唯一哨兵验证 MySQL、Redis、etcd、S3、Milvus 跨停止/启动持久化，成功后精准删除。
- 兼容修正：SeaweedFS multipart abort 接受 AWS 404 或严格空且未截断列表；Milvus 2.6 的 `index_files` 和旧 `index_log` 均能被索引对象检查识别。

### M01.3：环境分层

- 新增：`deploy/environments/dev.yaml`、`test.yaml`、`prod.yaml`、`scripts/infra_settings.py`、`tests/unit/test_infra_settings.py`。
- 约束：dev 仅 `127.0.0.1` 与本机忽略密钥；test 仅合成数据和临时密钥文件；prod 必须 TLS、外部密钥文件和获批业务数据。配置文件无真实密钥。

### M01.4：统一生命周期、复现和文档

- 新增：`scripts/infra_images.py`、`tests/unit/test_infra_images.py`、`docs/testing/m01-final-validation.md`、本行为记录。
- 修改：`Makefile`、`scripts/ci.py`、`deploy/compose/README.md`、`README.md`、`CHANGELOG.md`、`docs/progress/task-ledger.md`。
- 入口：镜像 build/verify、config、up、health、status、restart-test、upgrade、stop。`upgrade` 强制重建容器但保留五个卷，验证五类哨兵后精准清理。

## 3. 本机忽略文件

目录：`F:\heima\ai\python\project\i\deploy\compose\secrets\`。创建或保留以下文件，均被 Git 忽略，值未输出：

| 文件 | 字节 | 时间 |
|---|---:|---|
| `mysql_root_password` | 65 | 2026-09-06 17:16 |
| `mysql_password` | 65 | 2026-09-06 17:16 |
| `redis_password` | 65 | 2026-09-06 17:16 |
| `redis_config` | 209 | 2026-09-06 17:16 |
| `seaweed_s3_config` | 973 | 2026-09-07 18:25 |
| `seaweed_security_config` | 559 | 2026-09-07 18:25 |
| `milvus_config` | 865 | 2026-09-07 18:25 |
| `milvus_root_password` | 65 | 2026-09-07 18:25 |

`deploy\compose\.env`（307 字节，2026-09-06 17:33）沿用既有实例标识和端口；升级存储时没有覆盖它。所有密钥创建函数使用独占写入并拒绝轮换或部分修复。

## 4. 下载与安装

### 下载到审计工作区（不提交 Git）

根目录：`C:\Users\111\Documents\智能电商客服重构\artifact_work\`。

| 文件 | 字节 | SHA-256 | 用途 |
|---|---:|---|---|
| `sources\gosu-1.19.tar.gz` | 17,622 | `CD9719B775DBFEDAE53923C9B0DC792B66D42C51E0B36652ED6F747FBADC0164` | MySQL 权限切换工具源码核验 |
| `sources\etcd-v3.6.14.tar.gz` | 7,389,983 | `A7AC1ED4192C6E53E4716DF3E08BC75E4F929FCB186A9D9E5B0AAF11C96B067A` | etcd 源码核验 |
| `toolchains\go1.27.1.windows-amd64.zip` | 78,931,360 | `A3911B5E0E1B1053F25ED0675F4C1C6AAD1E2BFCF253DF2B9BE4CAABD2EDD95D` | 本地依赖审计；解压目录在同级 `go1.27.1-windows-amd64\` |

Milvus v2.6.23 与 SeaweedFS 4.45 的固定源码、Go 工具链和基础镜像由 Docker 构建按各自 `source.lock.json` 下载并校验。拉取/使用的构建或运行基础包括固定 digest 的 MySQL 8.4.11、Redis 8.8.2、Go 1.27.1 Alpine、Milvus v2.6.23、Milvus build environment、Alpine 3.24.1，以及 Trivy 0.74.0；未推送到任何 registry。

### 安装到独立 Conda 环境

环境：`F:\heima\ai\python\day01\Anaconda\envs\intelligent-commerce-support-v1`。按 `ci/infra-requirements.lock` 哈希安装运行探针依赖；核心直接依赖版本为 boto3 1.43.89、PyMySQL 1.2.0、redis 8.1.0、pymilvus 2.5.18，并带入 botocore 1.43.89、grpcio 1.83.1、numpy 2.5.2、pandas 3.0.5、protobuf 7.36.1、ujson 6.0.0 等锁定传递依赖。未修改 base Conda 环境。

## 5. Docker 写入

### 最终运行镜像

| 服务 | 本地镜像 ID | 大小（字节） | HIGH/CRITICAL |
|---|---|---:|---:|
| MySQL | `sha256:30522be8a94e195f37d43a72638449d206a0b0ce57f9502f8999cdef8cfa9ec5` | 267,722,340 | 0/0 |
| Redis | `sha256:a3bf2dc42d377fd2afbe6e620d0a948b1f4ecc9fba88df84a7eef9cced1c7788` | 40,148,324 | 0/0 |
| etcd | `sha256:0ffa356147517f233a637a66505730876595746db5d1850401ee5611e7fbd6b2` | 46,377,883 | 0/0 |
| SeaweedFS | `sha256:dfac2e817ad5b9b2c6ee725127905f3893787089690318772c942f4239989c00` | 49,251,364 | 0/0 |
| Milvus | `sha256:224967fbdaa1303852bf821cd48f5255078fb1552795065eb33bb79ec652c1b1` | 505,066,084 | 0/0 |

证据目录：`artifact_work\infra-maintained-evidence\`、`milvus-evidence\` 和既有 `seaweedfs-evidence\`。最终 Milvus tar 为 `ics-milvus-final.tar`（SHA-256 `E9D1D91AD018B65FE91AD8A6F5624FA214D76B5F6236BE8B0ED7C53DE7981003`），报告为 `ics-milvus-final.trivy.json`（SHA-256 `451A7176562F164977C0F3921E9B7C40749A01A85DCA03B936386B7E2AB91EDE`）。MySQL 最终证据为 `mysql-final.tar` 和 `mysql-final.trivy.json`；Redis/etcd 对应同名 tar/json。

Milvus 首次导出包含 BuildKit attestation，严格归档绑定校验拒绝；随后以 `--provenance=false --sbom=false` 重建、重新导出、重新扫描并通过。没有降低扫描严重度或忽略未修复漏洞。

### 运行资源

- 容器：`ics-v1-dev-mysql-1`、`redis-1`、`etcd-1`、`seaweedfs-1`、`milvus-1`；最终均 healthy。
- 命名卷：`ics-v1-dev_mysql_data`、`redis_data`、`etcd_data`、`seaweedfs_data`、`milvus_data`。
- 网络：`ics-v1-dev_infra`（内部）与 `ics-v1-dev_local`（宿主 loopback 桥）。
- 固定桶：`ics-knowledge`、`ics-milvus`。
- 测试数据：只写随机唯一合成键/对象/collection；成功后删除。工具表 `_m01_infra_smoke` 与 `_m01_persistence` 保留为空表，便于重复探针，不含业务数据。

## 6. 问题、判断与修正

1. 公开上游候选扫描发现高危漏洞，因此未直接采用；分别构建安全派生镜像并保留原始候选报告。
2. SeaweedFS 默认 `volume.max=8` 在两桶和多 collection 探针下耗尽，改为 32 后真实闭环稳定通过。
3. 旧三服务卷由 root 创建，非 root etcd/SeaweedFS 无法写入；新增只针对两个精确归属卷的临时 helper 修正 UID 1000 所有权，不删除数据。
4. SeaweedFS multipart abort 与 AWS 返回差异、Milvus 2.6 对象目录变化均通过严格兼容分支处理，没有放宽到“任意成功”。
5. Docker Desktop 在验证期间重启过一次；随后确认原 KF 六服务全部恢复 healthy，再继续新平台验证。
6. 首次完整 M01 推送 `70ceb7513be9e76b3dad5f5a08804733676bcc79` 的运行 `34122732595` 因纯 CI 环境缺少 boto3 导入失败，未伪装成功；修正为仅在实际 S3 初始化时加载运行 SDK。
7. 修正提交 `3dc1b003dbe81903364792e27f54e663e48d76a0` 的运行 `34123971915` 中，双平台基础门禁和四个镜像通过，Milvus 在第三方 GNU libiconv 官方镜像 502/超时后失败；新增最多三次、间隔 15 秒的同命令有界重试，第三次仍失败即阻断，未放宽扫描。
8. 有界重试提交 `81d9738c7acda59c67671def316f72abf652462f` 的运行 `34127584714` 中，Milvus 在单线程 OpenBLAS/C++ 依赖编译时达到 90 分钟并被取消；日志显示仍在正常编译而非测试失败。考虑同一配方本地真实构建约 53 分钟、GitHub 双核 runner 性能差异及重试预算，将单镜像硬上限调整为 180 分钟；仍禁止无限运行和跳过扫描。

## 7. 最终验证

- `scripts/ci.py`：PASS；结构、治理、48 条规则/93 条用例文档引用、CI/Compose 静态守卫、Ruff 与 203 个单测全部通过。Windows 因宿主权限跳过 5 个符号链接用例，Linux CI必须执行。
- `scripts/local_infra.py health`：PASS；MySQL/Redis/etcd 认证写读删，S3/Milvus 45 项合成契约通过。
- `restart-test`：PASS；五类数据跨 stop/start 保留并清理。
- `upgrade`：PASS；五类数据跨五容器强制重建保留并清理。
- `infra_images.py verify`：PASS；五镜像 ID 与 `images.lock.json` 一致。
- 原 KF：`knowforge-api`、`knowforge-mysql`、`knowforge-redis`、`knowforge-etcd`、`knowforge-minio`、`knowforge-milvus` 最终均 healthy。

## 8. 不可变资产复核

| 原始文件 | 最终 SHA-256 | 结果 |
|---|---|---|
| `F:\heima\ai\python\home\intelligentAssistant.zip` | `1A902066CAC9C4E3F0F508FC849F6B511A395BFA2458519C88AA6B84A68E7DF4` | 与基线一致 |
| `F:\heima\ai\python\home\intelligentAssistant_backup_60passed.zip` | `C9E85DFC65B506E2F44C5240581934C691E94EAFBF6417A6928E6F8EF37B001C` | 与基线一致 |
| `F:\heima\knowforge-rag-platform.zip` | `17B87DC3E0EAAF8DFFF6FEC4F9B23C2EDF734128B38CABC4281F9DE659FE967F` | 与基线一致 |

## 9. GitHub 交付

分支：`codex/v1-greenfield`，远端：`sy824869109/intelligent-commerce-support-v1`。M01 主实现提交为 `70ceb7513be9e76b3dad5f5a08804733676bcc79`，运行期 SDK 边界修正为 `3dc1b003dbe81903364792e27f54e663e48d76a0`，有界下载重试提交为 `81d9738c7acda59c67671def316f72abf652462f`。最终 180 分钟预算修正和 Actions 运行链接以本文件所在分支的后续提交及最终交付回复为准；历史失败/取消运行均保留，未删除或重跑成假成功。
