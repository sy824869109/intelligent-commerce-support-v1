# M01 存储安全评估增量（2026-09-07）

状态：**M01.1 IN_PROGRESS**。本增量只交付离线可验证的存储配置生成器、合成数据探针和哈希锁定的验收 SDK；不代表已经运行五服务，不推进 M01.2。

## 已完成的评估

- 精确 SeaweedFS 4.45 官方镜像通过 Trivy 0.74.0 扫描，结果为 **2 HIGH、23 UNKNOWN 包实例条目**，不能准入。两个 HIGH 分别来自 Apache Thrift 旧替换版本和 WebP 解码依赖；完整报告保留在本地忽略目录 `data/m01-reports/seaweedfs-4.45.json`。
- 源码确认 4.45 已包含此前 ACL、tagging 和独立 IAM 修复，但 Filer IAM gRPC 的身份验证仍需要显式配置，不能只据公告版本字段判断默认安全。
- 原定 Milvus 2.5.15 存在两项官方认证绕过。2.5.27 虽修复这两项，完整扫描仍有 **3 CRITICAL、51 HIGH 包实例条目**，不能据补丁号放行。完整报告为 `data/m01-reports/milvus-2.5.27-public-image.json`。
- Milvus 首次扫描因默认时间不足失败；使用更长有界扫描实际完成后才记录上述结果。失败不记 PASS，不删漏洞、不用网络超时充当鉴权拒绝。
- SeaweedFS 依赖修补派生构建和其他维护版本核查仍在进行中，未提供最终生产安全结论。

## 本次可复用成果

`scripts/storage_config.py` 是无 I/O 的生成与校验函数，输出独立知识桶/索引桶账号、内部签名配置和 Milvus 开启认证的配置。它本身不写密钥、不启动服务、不读取旧 KF。

`scripts/storage_probe.py` 只在显式调用时使用 SDK，固定两桶，所有数据为 UUID 命名的合成样本，精确清理本次对象/集合。包括：

- SigV4 PUT/GET/HEAD、Range、分页、SHA-256、分片完成/取消。
- 匿名/错误签名、跨桶读写/列表/删除/CopySource 拒绝；同名嵌套对象隔离。
- 安全小图片带缩放参数仍返回原字节，不运行资源耗尽攻击样本。
- 2048 行 HNSW、索引完成状态、查询目标 ID、数据日志与索引对象的实际对应关系。
- Milvus 匿名和错误 root 拒绝；网络错误不算鉴权证据。
- 显式持久化 prepare/verify/cleanup API；调用这些函数本身不证明容器重启，重建证据必须在 M01.2 另外保存。

`tests/unit/test_storage_probe.py` 的 23 个单元测试使用内存 mock 验证探针自身逻辑，包括反例和失败清理。**这 23 个测试不是 S3/Milvus 真实兼容通过，也不是 93 条业务验收。**

`ci/infra-requirements.lock` 由 uv 0.12.10 编译，所有传递依赖含 SHA-256；使用新平台独立 Conda 环境。未改原 KF 环境，未升级其 LangChain/模型或检索代码。

## 边界与下一步

现有已验收运行范围仍为新平台 MySQL/Redis/etcd 三服务。原项目和 KF 运行资产均不修改。后续必须完成安全候选处置、镜像构建复扫、五服务认证与真实读写检索、保卷重建、环境分层和生命周期脚本，才能逐卡宣布 M01 完成。

官方证据：[SeaweedFS 发布](https://github.com/seaweedfs/seaweedfs/releases/tag/4.45)、[ACL 修复](https://github.com/seaweedfs/seaweedfs/commit/311bc3a6dfbd042751692bc3de8accc516fcf8c1)、[Thrift 公告](https://github.com/advisories/GHSA-8wv5-x4w7-5gww)、[WebP 公告](https://pkg.go.dev/vuln/GO-2026-6222)、[Milvus Proxy 公告](https://github.com/milvus-io/milvus/security/advisories/GHSA-mhjq-8c7m-3f7p)、[Milvus 9091 公告](https://github.com/milvus-io/milvus/security/advisories/GHSA-7ppg-37fh-vcr6)。
