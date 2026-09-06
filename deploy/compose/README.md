# M01.1 本机基础设施（当前为三服务子集）

可执行文件是 `infra.compose.yml`，只有 MySQL、Redis、etcd。**M01.1 仍 IN_PROGRESS**：用户选择先评估受维护 S3 替代；旧 MinIO 和 Milvus 没有可执行配置，也没有启动。见 [ADR-0004](../../docs/decisions/ADR-0004-object-storage-security-gate.md) 和 [候选评估](../../docs/operations/s3-alternative-evaluation.md)。

## 运行边界

- 开发根目录：`F:\heima\ai\python\project\i`，使用既有独立 Conda 环境和 PyCharm。
- 使用本机 Docker Linux Engine，不改变当前 context，拒绝远程 daemon；本机版本见 [测试证据](../../docs/testing/m01-1-infrastructure.md)。使用 Compose Specification，不是旧 Python Compose v1。
- `ics-v1-dev` 独立 project、三份命名卷、内部网络及本机访问桥，不复用原 KF 资源。etcd 只接内部网络；MySQL/Redis 增加专属 bridge 以支持宿主 loopback 映射。这不是全服务出站隔离方案。
- MySQL `127.0.0.1:23306`，Redis `127.0.0.1:26379`；etcd 不发布宿主端口。当前没有局域网页面/API，不是 V1 上线。
- 镜像固定 tag 与 OCI index digest，清单为 `images.lock.json`。digest 验证不等于漏洞扫描完成。

## 首次启动（项目根目录的 PyCharm 终端）

激活 `intelligent-commerce-support-v1` Conda 环境，确认 `python --version` 是 `3.12.14`。

```powershell
python scripts/local_infra.py init
python scripts/local_infra.py config
python scripts/local_infra.py up
python scripts/local_infra.py smoke
python scripts/local_infra.py status
```

本机本轮已经执行 `init`，后续不要重跑；脚本拒绝覆盖已有凭据。其他电脑首次使用需按 [锁文件](../../ci/requirements.lock) 安装验证工具：

```powershell
python -m pip install --require-hashes --only-binary=:all: -r ci/requirements.lock
```

`init` 在本目录创建 `.env` 和 `secrets/`，三套密码分别随机生成 32 字节熵，不输出终端。`.env` 只有数据库、端口与非秘密实例 ID；应用根目录 `.env.example` 暂不改变，不能把两套模板混用。

`INFRA_INSTANCE_ID` 标识本地实例。容器、网络、卷带同一标记；启动前拒绝未知同名资源，包括没有容器的孤立卷。换电脑要重新 init，不要复制他人 `.env` 后接入同名卷。

## 验证与停止

```powershell
python scripts/verify_infra.py
python scripts/ci.py
python scripts/local_infra.py smoke
python scripts/local_infra.py stop
```

- `smoke` 在新 MySQL 开发库建立 `_m01_infra_smoke` 工具表，写/读/删除本次唯一合成行；不建立业务模型。Redis 探针带 60 秒 TTL 并删除，etcd 只操作本次唯一 `/ics/m01/probe/` 键，不删除他人数据。
- 检查 MySQL 应用账号读写和无密码拒绝、Redis 认证读写和匿名拒绝、etcd 内部健康/读写。三服务健康不代表 S3/Milvus 或 93 条业务验收通过。
- `stop` 不读取密钥或 Compose 配置；密钥丢失时仍只停止已验证属于本目录/project 的精确容器，保留容器与卷。
- 再次 `up` 复用同一实例的卷。修改 MySQL 密码文件不会自动修改已有库用户密码；不要重新生成凭据或删卷“修复”认证失败。
- 不提供删卷命令；不要执行 `down -v`、全局 prune、停止全部 Docker 容器。

## 安全与未完成项

Linux 密钥目录 0700，文件 0644，以支持容器内非 root 读取只读 secret；其他宿主用户不能穿过目录。Python 3.12.14 在 Windows `mkdir(0o700)` 设置受限 ACL，本机已核查。Compose 本地 secret 是文件挂载，不是加密密钥库；Docker/本机管理员仍可读取。不得放宽 ACL，不提交 `.env`/`secrets/`，不要回显完整 Compose 配置、容器环境或密码文件。

脚本不透传服务或 Compose 参数，拒绝 `COMPOSE_*`/Docker 目标覆盖；shell 的数据库环境值不能覆盖专用 `.env`。静态守卫不是完整 SAST、镜像 CVE 扫描或权限审计。

M01.2 仍需完整初始化、重建持久化与故障恢复；M01.3 负责配置分层/密钥轮换；M01.4 再完成正式统一启动/健康/无损升级工具。本次只是当前子集的最小安全验证入口，不提前标记后续任务完成。
