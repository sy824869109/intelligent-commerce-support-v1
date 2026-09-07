# SeaweedFS 4.45-m01-security.1

新平台独立安全派生构建，不是官方原版镜像，不修改原 KF、旧项目或参考压缩包。上游业务源码不变，仅修改三项 Go 依赖与对应校验和；保留 Apache-2.0 LICENSE 和构建信息。

## 固定输入

- 上游：`4.45`，提交 `79b87202136cebdaaa7db4d94eaa5915ad381276`，归档 SHA256 见 `source.lock.json`。
- 工具链：官方 Go `1.27.1-alpine3.24`，禁止工具链自动下载；最终基础镜像官方 Alpine `3.24.1`，均固定 manifest index digest。
- 构建类型遵循上游 `normal`：空 build tags、`CGO_ENABLED=0`。不构建 Rust Volume/Worker、Enterprise、插件或 full/rclone 变体。
- Apache Thrift：去掉旧伪版本 replace，使用已声明的 `v0.24.0`；`x/image v0.45.0`；`x/crypto v0.56.0`。
- `dependencies.patch` 为相对上游的最小差异；`go.mod.lock` / `go.sum.lock` 是应用该差异后的完整模块文件，构建时直接复制，避免给最小构建器额外安装 patch 工具。`modules.sha256` 锁住两个文件，构建前后验证哈希、`go mod verify`、`-mod=readonly`。
- Go 工具链将模块语言指令 `go 1.26` 规范化为 `go 1.26.0`，不改变语言版本。`go.sum` 保留上游历史校验项，不代表旧版本被链接；实际版本以镜像内 `weed.buildinfo.txt` 为准。
- 最终镜像不执行 APK 安装/升级，不含 curl/libcurl 或编译器。首次复扫发现 Alpine 基线 OpenSSL 3.5.7 仍有告警；静态 Go 服务不使用这些库，因此离线移除包管理器、ssl_client 及 libssl3/libcrypto3 后重新扫描。保留 musl/BusyBox 和 CA bundle；Go TLS 使用自身实现，健康检查仅调用 HTTP loopback。

## 构建

在本目录执行：

```powershell
docker build --platform linux/amd64 --progress plain -t intelligent-commerce/seaweedfs:4.45-m01-security.1 .
docker run --rm intelligent-commerce/seaweedfs:4.45-m01-security.1 version
```

首次模块下载与静态编译耗时较长。无 `latest`、不执行 `go get -u` 或 `go mod tidy`，不拉取浮动分支；修改锁定输入必须重新评审与扫描。重现范围为固定源码、工具链、依赖和配置输入，不承诺 Docker 构建时间元数据导致的镜像 ID 字节一致。

## 运行边界

裸运行仅显示版本，不自动启动匿名服务。必须通过审查后的 Compose 密钥校验入口启动 `weed server`：内部 Master/Filer/Volume HTTP/gRPC 只绑定容器 loopback，S3 单独绑定容器网络，宿主仅回环端口。

必须显式禁用独立/嵌入 IAM、SFTP、WebDAV、MQ、Iceberg/Lance 监听端口、遥测、JPG 方向修正与不可信 remote endpoint；使用非空静态 S3 身份配置与随机 Filer JWT 管理签名 key。普通业务身份无全局 Admin、无 ACL/表管理权限，不创建表桶。

镜像 `USER 1000:1000`，数据卷初始化属于该用户；外置只读 secret 必须允许该用户读取，不以将整个运行服务改回 root 解决权限问题。正式 Compose 应负责只读根文件系统、`/tmp` tmpfs、资源限制和只读 secret 挂载；尚未通过整套存储准入前不提供可运行配置。

依赖修复不替代 S3/Milvus 契约、权限负向、故障恢复、持久化测试。扫描中 UNKNOWN/无修复通告应保留适用性说明，不能把一次扫描或构建成功称为企业生产安全认证。

## 来源与许可证

[上游构建 recipe](https://github.com/seaweedfs/seaweedfs/blob/79b87202136cebdaaa7db4d94eaa5915ad381276/docker/Dockerfile.go_build)、[normal/full 构建区分](https://github.com/seaweedfs/seaweedfs/blob/79b87202136cebdaaa7db4d94eaa5915ad381276/.github/workflows/container_release_unified.yml)、[Go 稳定发行](https://go.dev/dl/)、[Apache-2.0 LICENSE](https://github.com/seaweedfs/seaweedfs/blob/79b87202136cebdaaa7db4d94eaa5915ad381276/LICENSE)。

镜像内 `/usr/share/licenses/seaweedfs/` 保存 LICENSE、派生说明、源锁和 `go version -m` 构建信息。再分发时保留相关声明，第三方依赖许可另行清点。本说明为工程记录，不构成法律保证。
