# M01 最终验收记录（2026-09-07）

## 结论

M01.1–M01.4 的本地开发基础设施已实施完成：五服务静态边界、真实健康、认证读写、对象/向量闭环、停止重启持久化、强制重建持久化、环境分层和镜像安全门禁均通过。原 KF 与旧项目未作为运行依赖，也未被修改。

## 验收结果

| 门禁 | 结果 | 证据摘要 |
|---|---|---|
| Compose 静态边界 | PASS | 正好五服务；固定 digest；loopback 端口；etcd 仅内部网络；无明文密码、特权模式和宿主数据目录 |
| 五服务运行健康 | PASS | MySQL、Redis、etcd、SeaweedFS、Milvus 均为 running/healthy |
| 主机可达性 | PASS | 23306/26379/28333/29530 的协议或连接检查通过 |
| 认证与数据闭环 | PASS | MySQL、Redis、etcd 认证写读删；S3/Milvus 共 45 项合成契约通过 |
| 停止/启动持久化 | PASS | 五类唯一哨兵跨 stop/start 保留，随后精准删除 |
| 强制重建持久化 | PASS | 五类唯一哨兵跨 `--force-recreate` 保留，随后精准删除 |
| 环境分层 | PASS | dev/test/prod 三份无密钥配置通过；dev 仅 loopback；prod 强制 TLS/外部密钥契约 |
| 镜像安全 | PASS | 五个本地镜像均与锁定 ID 一致，完整 tar 扫描 HIGH=0、CRITICAL=0 |
| 本地质量门禁 | PASS | 结构、治理、48 条标准引用、格式、静态检查和 204 个单测通过；Windows 权限限制导致 5 个符号链接用例跳过，由 Linux CI 覆盖 |

## 真实闭环示例

健康探针以一次性随机 ID 写入 MySQL 表、Redis 键、etcd 路径、`ics-knowledge` 对象和 Milvus 临时 collection；向量索引产生的对象还必须出现在 `ics-milvus` 桶。读取与权限隔离验证后，只删除本次 ID 对应的数据。重启与升级演练在服务停止前写入同类哨兵，恢复后逐项核对再清理。

## 尚未声称完成

M01 是基础设施层，不包含 FastAPI 业务服务、前端、KF RAG 适配、Agent、知识图谱或局域网业务页面。93 条业务验收仍为 NOT_RUN；下一任务是 M02.1。
