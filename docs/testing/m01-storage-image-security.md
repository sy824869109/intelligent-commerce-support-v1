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

## 本地镜像证据入口（本次已实跑）

在项目独立 Conda 环境、项目根目录运行：

```text
python scripts/storage_image.py build
python scripts/storage_image.py verify
```

两个命令均已在本机实际通过。它们只构建/扫描/校验镜像，不启动 S3 或 Milvus，尚未接入现有三服务 Compose。失败不会生成新的通过记录；已有记录必须独立通过验证，不能仅检查文件存在。

更新镜像 README 后再次构建/复扫/验证通过，本次 manifest ID 为 `sha256:dfac2e817ad5b9b2c6ee725127905f3893787089690318772c942f4239989c00`，仍为 0 HIGH/CRITICAL、1 UNKNOWN。前文 ID 是首次配方验证的历史证据；当前实际 ID/config/报告以本机 `data/m01-reports/storage-image-lock.json` 及 verify 成功结果为准。

证据链为：固定构建配方 → 本机 Docker 镜像 ID → 导出归档及内容哈希 → config ID → 完整扫描报告。兼容 Docker 29 的 manifest ID 与旧 Docker 的 config ID；拒绝归档篡改、错误报告、过期记录、路径逃逸和缺失扫描目标。记录默认 7 天失效，但有效期不代表期间不存在新漏洞。报告与记录保留在本机忽略目录，不提交 Git。

新增 44 个单元测试；本机 Windows 其中 5 项真实符号链接用例因权限不足明确跳过，不能计为通过。其余 39 项通过，Linux CI 另外验证符号链接分支。

本次完整 `scripts/ci.py` 已通过：178 项中通过 173、跳过 5；结构、治理、静态检查、格式和差异检查通过。93 条业务验收仍为 NOT_RUN。

构建配方提交 `501766a` 已推送；[CI 34071349513](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34071349513) 的 Windows、Linux、真实镜像构建及 HIGH/CRITICAL 扫描全部成功。此运行不包含随后新增的本地证据入口测试。

## 剩余安全阻断与实施边界

S3/Milvus 实际服务和读写/检索尚未运行，持久化与环境/生命周期卡未完成。Milvus 2.6.23、etcd 3.5.33 的完整扫描仍有 Go/gRPC 依赖告警；其中 Milvus 普通 gRPC 传输链路的 HTTP/2 接收缓冲风险发生在鉴权之前，不能仅靠密码或私网声明修复。

来源：[gRPC 官方公告](https://github.com/grpc/grpc-go/security/advisories/GHSA-vp52-pcj8-j9qc)、[Milvus 2.6.23 服务实现](https://github.com/milvus-io/milvus/blob/v2.6.23/internal/distributed/proxy/service.go)、[Go SSH 通告](https://pkg.go.dev/vuln/GO-2026-6303)。SSH 条目与普通 gRPC 条目须分别研判，不能将模块存在一概等同可利用，也不能将全部告警一概忽略。

最新候选的本地完整扫描包实例计数如下；重复实例不是独立漏洞数量，也不等于全部可利用：

| 候选 | CRITICAL | HIGH | 本机报告（data/m01-reports/） |
|---|---:|---:|---|
| Milvus 2.6.23 | 2 | 78 | milvus-2.6.23-public-image.json |
| etcd 3.5.33 | 3 | 24 | etcd-3.5.33-public-image.json |
| Redis 8.2.9 Alpine | 0 | 8 | redis-8.2.9-alpine-public-image.json |
| Oracle MySQL 8.4.12 | 0 | 5 | mysql-8.4.12-oracle-public-image.json |

以上是候选评估，不是现有三服务部署已更新或已完成整套安全验收。未覆盖原 KF 容器，也未修改它们。

只读源码核查表明，Milvus 的 `Makefile` 虽有单独 `build-go`，但明确要求 CGO 和已有 C++ 产物；`internal/storagev2/packed/ffi_common.go` 要求 `milvus_core` / `milvus-storage`，`type.go` 引用 Arrow C ABI。源码固定在 `bfa1bc34f93df2ccd20fa7c060463c6c6812d355`。不能把 SeaweedFS 的纯 Go 静态构建配方直接套到 Milvus，也不能只更新镜像系统包就宣称修复二进制内的 gRPC。

若要继续自建修补版 Milvus，需补充可复现 C++/Go 构建、依赖来源与 ABI 验证、许可证、性能与数据兼容回归，以及后续安全补丁维护责任。这超出普通镜像版本替换；本次没有开始该构建，没有修改 KF 检索核心，也没有降低准入门槛。需用户确认是否承担此维护方向，再继续 M01.1；M01.2–M01.4 和 93 条业务验收仍未完成。
