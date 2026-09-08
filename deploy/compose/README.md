# M01 本地基础设施运行手册

M01 已形成独立的五服务开发底座：MySQL、Redis、etcd、SeaweedFS S3 和 Milvus。它只属于新平台 `ics-v1-dev`，不复用、不修改原电商客服或 KF RAG 的容器、源码、配置和数据。

## 数据链路

`本地应用（后续 M02） → 127.0.0.1 → MySQL / Redis / S3 / Milvus`。Milvus 在内部网络访问 etcd 保存元数据，并使用 SeaweedFS 的 `ics-milvus` 桶保存对象；知识文件使用隔离的 `ics-knowledge` 桶。etcd 不向宿主机发布端口。

## 首次准备

在项目 Conda 环境、项目根目录执行：

```powershell
python -m pip install --require-hashes --only-binary=:all: -r ci/requirements.lock
python -m pip install --require-hashes --only-binary=:all: -r ci/infra-requirements.lock
python scripts/infra_images.py build
python scripts/local_infra.py init
python scripts/local_infra.py up
python scripts/local_infra.py health
```

`infra_images.py build` 只构建五份已审查配方，不发布或删除镜像，并要求产物 ID 与 `images.lock.json` 完全一致。`init` 只在本机首次创建 `.env` 和八个忽略文件；存在任何配置时拒绝覆盖。旧三服务开发实例升级时只执行一次 `init-storage`。

## 日常命令

```powershell
python scripts/local_infra.py config
python scripts/local_infra.py up
python scripts/local_infra.py health
python scripts/local_infra.py status
python scripts/local_infra.py restart-test
python scripts/local_infra.py upgrade
python scripts/local_infra.py stop
```

- `health`：真实认证读写 MySQL/Redis/etcd，执行完整 S3/Milvus 合成契约并精准清理。
- `restart-test`：五类存储写入唯一哨兵，停止并原样启动，验证持久化后删除哨兵。
- `upgrade`：写入同类哨兵，强制重建五个容器但保留卷，验证并清理；这是基础设施升级机制演练，不代表业务数据库迁移完成。
- `stop`：只停止归属标签、工作目录和服务白名单都匹配的容器；永不删除卷。

Makefile 同步提供 `infra-images`、`infra-config`、`infra-up`、`infra-health`、`infra-stop`、`infra-restart-test` 和 `infra-upgrade`。

## 边界与故障处理

- 宿主端口固定为 MySQL `23306`、Redis `26379`、S3 `28333`、Milvus `29530`，全部绑定 `127.0.0.1`；因此 M01 本身不提供局域网业务入口。
- 本机密钥不能提交、复制给别人或输出到日志。开发配置仅允许合成数据；生产配置声明 TLS 和外部密钥文件契约，但 M01 不部署生产环境。
- 镜像必须是 `images.lock.json` 中的本地 digest；Compose 使用 `pull_policy: never`，不会悄悄替换镜像。
- 不要执行 `down -v`、全局 prune、停止全部容器或删除卷。密钥丢失、卷归属不符、镜像摘要不符时先保留现场。
- SeaweedFS 4.45 在 multipart abort 后可能返回严格空列表而非 AWS 404；探针只接受这两种无残留结果。Milvus 2.6 使用 `index_files` 对象路径，探针同时兼容旧 `index_log` 以识别真实索引对象。

完整验收与行为记录见 `docs/testing/m01-final-validation.md` 和 `docs/operations/m01-implementation-behavior-log-20260907.md`。209 个工具单测和 45 项 S3/Milvus 合成检查不等于 93 条业务验收；业务用例仍为 NOT_RUN。完整五镜像远端运行 `34153937684` 已成功，但 Milvus 单项耗时约 2 小时 35 分；因此每次 push 只真实构建并扫描 MySQL、Redis、etcd、SeaweedFS，Milvus 完整源码审计只在带 `ics-image-builder` 标签的受控 Linux 构建机上人工触发。push 中跳过状态保持可见，不能写成一次新的远端 Milvus 审计通过。
