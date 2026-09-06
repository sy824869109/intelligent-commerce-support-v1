# M01.1：S3 兼容对象存储初步评估

日期：2026-09-06。状态：**只读评估完成；选型未生效，兼容验证 NOT_RUN**。用户要求先评估受维护替代，不能据此直接部署或接受商业许可。原 KF 源码、原 MinIO 数据和原运行容器不变。

## 初步建议

优先进入 **SeaweedFS 4.45** 精确版本安全/兼容验证，Garage 2.3.0 备选。RustFS 官方版本仍是 RC，不进入稳定版准入。理由是功能覆盖和可核查的 Milvus 集成参考，不是“它最新”。

| 候选 | 维护/许可证据 | 优点 | 当前限制与结论 |
|---|---|---|---|
| SeaweedFS 4.45 | 官方 2026-08-31 发布；Apache-2.0 | 单机 `weed mini` 和 S3 服务；有 NVIDIA 官方 Milvus 集成配置 | 首选待测；不能默认匿名 Allow All，不公开 Master/Filer/Admin；近期安全公告仍需核对 |
| Garage 2.3.0 | 官方 stable tag 2026-04-16，近期仍维护；AGPLv3 | 轻量、单节点路径、基本对象/分片上传能力 | 缺标准 Bucket Policy/ACL、对象版本、Object Lock；不能假定这些语义存在；许可待确认 |
| RustFS 1.0.0-rc.5 | 官方 2026-09-02 预发布；Apache-2.0 | 活跃开发，官方有 Milvus 教程 | 仍为预发布，仅观察，不突破稳定版规则 |

来源：[SeaweedFS 发布](https://github.com/seaweedfs/seaweedfs/releases/tag/4.45)、[许可证](https://raw.githubusercontent.com/seaweedfs/seaweedfs/4.45/LICENSE)、[单机文档](https://github.com/seaweedfs/seaweedfs/wiki/Quick-Start-with-weed-mini)；[Garage 标签](https://github.com/deuxfleurs-org/garage/tags)、[许可证](https://raw.githubusercontent.com/deuxfleurs-org/garage/v2.3.0/LICENSE)、[兼容矩阵](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/)、[已知限制](https://garagehq.deuxfleurs.fr/documentation/reference-manual/known-issues/)；[RustFS 发布](https://github.com/rustfs/rustfs/releases/tag/1.0.0-rc.5)、[许可证](https://raw.githubusercontent.com/rustfs/rustfs/1.0.0-rc.5/LICENSE)。许可证信息只记录来源，不替代项目许可审查。

## Milvus 兼容：配置能力不等于运行证据

[Milvus 2.5.15 精确配置](https://raw.githubusercontent.com/milvus-io/milvus/v2.5.15/configs/milvus.yaml) 保留 `minio` 配置名称，但支持自定义 S3 endpoint、region、凭据、TLS、bucket、rootPath、cloudProvider 和 path-style。这允许替换存储实现，不需要改 KF 检索核心；不代表每个 S3 产品都完全兼容。

- [NVIDIA RAG Blueprint 配置](https://raw.githubusercontent.com/NVIDIA-AI-Blueprints/rag/main/deploy/compose/vectordb.yaml) 有 SeaweedFS 3.73 + Milvus 2.6.5，是有价值参考，但不是本项目 4.45 + 2.5.15 的验收证明。
- Garage 未找到对应本项目精确版本的官方集成验收；缺失证据不等于不支持。
- [RustFS 教程](https://docs.rustfs.com/en/developer/integration/big-data/milvus) 使用 alpha.83 + Milvus 2.6.0，并声明本地集成用途，不能照搬默认凭据或升级 Milvus。

Windows 评估的是 Docker Desktop/WSL 2 Linux 容器和命名卷，不是原生 Windows 服务支持承诺。

## 安全准入未完成

SeaweedFS 不能被描述为“已经确认安全的替代”。[GHSA-jw56-gm6j-34mp](https://github.com/seaweedfs/seaweedfs/security/advisories/GHSA-jw56-gm6j-34mp) 针对独立 `weed iam`，公告区分嵌入式 IAM；[GHSA-9x53-cjpr-m682](https://github.com/seaweedfs/seaweedfs/security/advisories/GHSA-9x53-cjpr-m682) 的 affected/patched 表述需结合精确提交核对。后续先形成“镜像/版本 × 启用功能 × 适用公告 × 修复证据”清单，不能只凭版本号或一句“最新已修复”。

旧 MinIO 暂停依据与用户决策见 [ADR-0004](../decisions/ADR-0004-object-storage-security-gate.md)。不把单节点不适用的其他漏洞混为实际阻断原因。

## 后续验证（全部 NOT_RUN，仍属于 M01.1）

| 顺序 | 内容 | 通过证据 |
|---|---|---|
| 1 安全与许可 | 精确稳定版本、官方 digest、安全公告/镜像扫描、许可确认 | 适用高危风险无未决项，明确允许隔离试验 |
| 2 隔离 | 新 project/空卷/合成数据、必填凭据、管理面不对外 | 不挂载或连接旧 KF/MinIO 资产 |
| 3 S3 契约 | SigV4、path-style、region、PUT/GET/HEAD、Range、分页、删除、分片完成/取消 | 字节哈希、错误码正确 |
| 4 负向权限 | 匿名、错误/过期签名、跨桶、缺凭据启动 | 失败关闭，不退化为匿名 |
| 5 Milvus 实测 | 2.5.15 + PyMilvus 2.5.18 + etcd 3.5.18；建库/插入/flush/索引/load/search | 对象落到指定 bucket/prefix，查回固定样本 |
| 6 故障与持久化 | 重启、存储暂断、错误凭据、上传中断、恢复检索 | 有界失败，不假成功、不静默丢数据 |
| 7 决策与同步 | 新 ADR、镜像清单、操作说明、图中组件名 | 通过后才采用，再完成五服务 M01.1 |

不提前升级 Milvus、LangChain 或模型；RAG 优化仍放 V1.5，Agent/知识图谱不在本次范围。
