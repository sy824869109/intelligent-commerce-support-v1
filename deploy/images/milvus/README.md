# Milvus 2.6.23-ics.1 安全派生构建

状态：构建候选，尚未准入 Compose。

## 固定边界

- 功能源码固定为 Milvus v2.6.23 签名提交 `bfa1bc34f93df2ccd20fa7c060463c6c6812d355`。
- 编译器为 Go 1.27.1；官方归档、Milvus 构建器、官方运行镜像均固定 SHA-256。
- 完整 `go.mod.lock` / `go.sum.lock` 替换上游模块文件，`modules.sha256` 在构建前校验。
- 主程序和 `libmilvus-planparser.so` 使用同一依赖锁，必须同时包含 gRPC-Go 1.83.1 和 Sonic 1.15.2。
- 最终层复用同一上游版本的 C++ 库和配置，仅替换两个 Go 制品，缩小 ABI 差异；运行兼容仍须实测。

## 修补依赖

直接安全目标为 gRPC-Go 1.83.1、Apache Thrift 0.24.0、x/mod 0.40.0、x/crypto 0.55.0。Go 最小版本选择进一步得到 x/net 0.58.0、x/text 0.41.0、OpenTelemetry 1.44.0 等传递升级。

Go 1.27 还要求 Sonic 1.15.2。Milvus 内嵌 etcd 3.5.23 仍调用旧版 `otelgrpc` 拦截器；Google Cloud 模块会通过最小版本选择把它提升到已删除该接口的 0.61.0。因此锁文件使用 Go `replace` 将实际实现固定为保留所需接口的 otelgrpc 0.60.0，同时核心 OpenTelemetry 使用 1.44.0；最终安全性仍以镜像复扫为准。构建门禁检查二进制中 `v0.61.0 => v0.60.0` 的替换记录，不能只检查根模块声明。镜像构建只预取主模块，其他模块由实际编译按需读取并按 `go.sum.lock` 校验，避免下载与产物无关的测试工具依赖。

`build-cpp` 与 `build-go` 必须顺序执行。并行运行这两个 Milvus 顶层目标会让 Go 链接在 C++ 库和 pkg-config 文件生成前启动，属于构建竞态，不作为有效失败或通过证据。

Conan 1 在构建中断后可能保留失效锁。配方对专用、独占的 BuildKit 缓存执行 `conan remove --locks` 后再构建；该操作只清理本配方缓存锁，不删除依赖，不访问容器或业务数据卷。

构建器对不同构建工具统一限制为最多两个并发任务：Go 使用 `GOFLAGS=-p=2`（同时保留只读锁等选项）和 `GOMAXPROCS=2`，Rust 使用 `CARGO_BUILD_JOBS=2`，Conan 使用 `CONAN_CPU_COUNT=2`，CMake 使用 `CMAKE_BUILD_PARALLEL_LEVEL=2`，普通 Make 使用 `MAKEFLAGS=-j2`。Milvus 的 `scripts/core_build.sh` 显式执行 `make -j ${jobs}`，因此另设小写变量 `jobs=2`。`build-cpp` 和 `build-go` 仍由 Dockerfile 中两个连续命令严格串行执行，并发只发生在各目标内部。

此前构建出现过 Docker RPC EOF 和引擎无响应；资源压力是待验证的可能原因，尚无证据认定为 OOM。限制并发用于降低资源峰值，不改变功能源码或依赖版本，也不能代替构建成功、安全扫描和运行验证。Docker 恢复后已检查原 KF 六个服务健康；新候选镜像未替换原服务。

未运行成功前不能写成 Milvus 已修复；构建成功后仍需对最终镜像完整复扫，并执行 ABI、启动、认证、S3 和向量契约测试。不得用 Trivy ignorefile 隐藏 HIGH/CRITICAL。

## 本机构建

从项目根目录运行：

```text
docker build --platform=linux/amd64 --progress=plain --tag ics-milvus:2.6.23-ics.1 deploy/images/milvus
```

首次构建会下载完整 Go、Conan、Cargo 和 C++ 依赖。Milvus 官方建议至少 8 GB 内存和 50 GB 可用空间；不要在原 KF 目录或其数据卷内构建。本配方固定依赖版本，但部分上游 Conan 包的远端制品来源仍须在构建证据中记录，完整供应链复现结论待实际构建后给出。

## 退出策略

后续官方 Milvus 镜像若同时满足安全和兼容门禁，优先切回官方发行并废弃自维护分叉。自维护期间每次安全公告、Go/Milvus 升级或锁文件变化都必须重新构建、扫描和回归。

详见 [ADR-0005](../../../docs/decisions/ADR-0005-maintained-milvus-security-build.md)。
