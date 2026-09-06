# M01.1 基础设施增量验收

日期：2026-09-06。任务：**IN_PROGRESS**。当前是五服务任务中的 MySQL/Redis/etcd 子集；对象存储和 Milvus 尚未启动。用户已选择先评估受维护 S3 替代，见 [ADR-0004](../decisions/ADR-0004-object-storage-security-gate.md)。

## 真实环境

| 项目 | 实测值 |
|---|---|
| 开发目录 | `F:\heima\ai\python\project\i` |
| Python | 项目 Conda 环境 3.12.14 |
| Docker Desktop | 4.88.1；Engine 29.7.2；Linux amd64 |
| Compose | v5.4.0，使用 Compose Specification |
| Docker context | `desktop-linux`；未切换用户 context |
| 新 project | `ics-v1-dev` |
| 新服务 | MySQL 8.4.11、Redis 8.2.6、etcd 3.5.18，精确 digest 见 images.lock.json |

## 已执行证据

| 检查 | 结果 | 范围 |
|---|---|---|
| 官方 registry tag/digest 核验 | PASS | 三个镜像，与锁文件一致；不是 CVE 扫描 |
| Compose 静态/本地配置验证 | PASS | 固定 project、镜像、端口、网络、命令、健康检查、归属和文件凭据 |
| 新配置与工具单元测试 | PASS，45 项 | 正常路径及重复键、浮动镜像、越界挂载、未知旧卷、假健康、跳过鉴权、坏凭据、远程 daemon 等负例 |
| 完整本地 Foundation CI | PASS，79 项 | 原 34 项 + 新 45 项；结构/治理/48 规则/93 用例引用/格式/静态通过 |
| 容器健康 | PASS，3/3 | 不代表五服务验收 |
| MySQL | PASS | 应用账号合成行写读删；无密码拒绝；宿主 23306 握手验证版本 |
| Redis | PASS | 认证合成键写读删；匿名拒绝；宿主 26379 协议负例 |
| etcd | PASS | 容器内 endpoint health、唯一合成键写读删；没有宿主端口 |
| 密钥目录 | PASS | Windows 受限且不继承父目录 ACL，只允许 owner/system/admin；未回显密钥 |
| 三份只读 ZIP | PASS | SHA-256 均与资产台账一致 |
| 停止后重新启动 | PASS | 三份命名卷保留，再次健康/宿主协议/认证读写通过；不是完整灾备或数据恢复验收 |
| 原 KF 运行状态 | 未被重启或修改 | 本次末尾六个 knowforge 服务仍 healthy、连续运行约 27 小时 |
| Git 密钥隔离 | PASS | `.env`、密码文件和 Redis secret 配置被现有忽略规则排除 |

### 发现并修正的问题

1. 仅检查容器归属会漏掉同名孤立卷。增加本地实例 ID 的容器/卷/网络标记和执行前比对，未知旧资源拒绝接入。
2. 静态守卫最初未固定完整 command/health/log rotation。新增精确合同和负例，拒绝 `--skip-grant-tables`、`CMD true` 健康检查等假通过。
3. 初次 internal-only 部署容器健康，但 Docker 实际端口映射为空、宿主不通。MySQL/Redis 增加本项目专属访问桥，仍显式 loopback 发布；etcd 仅保留内部网络。补宿主协议探针后通过。
4. 停止路径与密钥/配置解析解耦，配置损坏时可在核验精确容器归属后安全停止，不能清空卷。

## 重跑命令

在项目根目录激活 Conda 后运行：

```powershell
python scripts/verify_infra.py
python scripts/ci.py
python scripts/local_infra.py config
python scripts/local_infra.py up
python scripts/local_infra.py smoke
python scripts/local_infra.py status
python scripts/local_infra.py stop
python scripts/local_infra.py up
python scripts/local_infra.py smoke
```

首次使用另先执行 `init`，当前本机已初始化，不能重复生成凭据。不要运行删卷命令。

## 尚未通过或尚未实施

- S3 候选精确版本安全准入、镜像扫描、许可确认和 Milvus 兼容验证：NOT_RUN。
- MinIO 不启动，候选未采用，Milvus 2.5.15 保留兼容目标但未启动。
- M01.2–M01.4：未推进；本次最小工具不是完整升级/备份/恢复系统。
- 应用业务、租户/RAG/闭环/局域网端到端 93 条用例：仍 NOT_RUN。
- Foundation CI 的配置和工具测试不能冒充容器集成 CI、镜像完整安全审计或 V1 发布验收。
- Docker 管理员能够读取本地文件 secrets。权限方案不等于生产密钥库，轮换与应用配置分层留 M01.3。

## 交付记录

实现提交：`4774ce2bc24177ed542e240a58a7c6fbc9c5524c`，已推送 `origin/codex/v1-greenfield`。14 个配置/测试/文档文件，不包含密钥或参考资产。

[GitHub CI 34027009809](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34027009809) 对应上述精确实现提交，Windows/Linux Foundation 均 success；五个未实现应用/契约/安全审计/镜像 job 仍 skipped。CI 的 79 项是工具/配置验证，不会远程启动本机 Docker，也不是 93 条业务用例。

独立代码复核无剩余阻断项。本地真实三服务探针、停止/重启、保卷及原资产不变证据见上表。M01.1 仍 IN_PROGRESS；不能将部分交付标为五服务任务完成。
