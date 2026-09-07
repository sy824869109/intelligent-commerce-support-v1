# M01.1 安全派生镜像验证

日期：2026-09-07。**镜像构建增量完成不等于 M01 或存储兼容完成。**

## SeaweedFS 派生镜像

- 上游固定 SeaweedFS 4.45 `79b87202136cebdaaa7db4d94eaa5915ad381276`，原 KF 与上游业务代码不改。
- 修补 Thrift 0.24.0、x/image 0.45.0、x/crypto 0.56.0；Go 1.27.1 静态构建。完整依赖锁、差异和来源随 `deploy/images/seaweedfs/` 提交。
- 首次派生扫描仍发现 Alpine OpenSSL 3.5.7 高危。该静态服务无需此库，最终离线移除包管理器/ssl_client/OpenSSL，保留公共 CA 证书和 musl/BusyBox。没有删除扫描报告或隐藏包数据库条目。
- 最终本地 tag：`ics-seaweedfs:4.45-m01-security.1`。
- Docker 29 返回的 manifest ID：`sha256:94e0e773593db44abed23758dc239a7dc855d035d5bc4a6bddc4094cd15512f7`。
- 镜像 config ID：`sha256:205078e204deceb729c8351d2aa37d0d8e366cfd1563442ce953588316f45592`；与 Trivy 报告 `Metadata.ImageID` 一致。两种 ID 含义不同，不能直接相等比较。
- 最终完整扫描：**0 CRITICAL、0 HIGH、0 MEDIUM、0 LOW、1 UNKNOWN**，保留 `GO-2026-5932`（openpgp 未维护通告，无修复版本）。这不是“绝对安全”或正式生产准入证明。
- 原始报告：本地忽略目录 `data/m01-reports/seaweed-security-minimal.json`，对应扫描的镜像归档为同名 `.tar`；前两次失败报告保留。
- 最终镜像以 UID/GID 1000 运行，默认只输出版本，不自动开匿名 S3。只读、无网络、无额外 capabilities 的版本检查通过。

## GitHub 增量门禁

激活独立 Linux `image-build`：真实构建限定目录 → 导出镜像 → 精确 Trivy 0.74.0 镜像扫描；HIGH/CRITICAL 或扫描错误均失败，不忽略未修复条目，不使用 Docker socket/仓库/密钥挂载，不上传镜像，不扩大 GitHub token 权限。

Windows/Linux foundation 保持真实执行。后端、前端、运行契约、完整应用安全审计仍未实现，不会假装通过。新增镜像配方必须另行评审，不能借此自动放开所有 Dockerfile。

## 尚未通过的整套准入

S3/Milvus 实际服务和读写/检索尚未运行，持久化与环境/生命周期卡未完成。Milvus 2.6.23、etcd 3.5.33 的完整扫描仍有 Go/gRPC 依赖告警；其中 Milvus 普通 gRPC 传输链路的 HTTP/2 接收缓冲风险发生在鉴权之前，不能仅靠密码或私网声明修复。

来源：[gRPC 官方公告](https://github.com/grpc/grpc-go/security/advisories/GHSA-vp52-pcj8-j9qc)、[Milvus 2.6.23 服务实现](https://github.com/milvus-io/milvus/blob/v2.6.23/internal/distributed/proxy/service.go)、[Go SSH 通告](https://pkg.go.dev/vuln/GO-2026-6303)。SSH 条目与普通 gRPC 条目须分别研判，不能将模块存在一概等同可利用，也不能将全部告警一概忽略。
