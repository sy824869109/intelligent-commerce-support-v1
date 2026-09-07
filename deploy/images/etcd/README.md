# etcd 3.6.14 安全派生镜像

从 SHA-256 校验后的 v3.6.14 源码构建，将参与三个发行二进制的模块统一升级到已验证的 gRPC/Go 安全依赖，再输出无 shell 的 scratch 运行镜像。镜像仅供新平台 M01 使用，不修改原 KF。

本地准入镜像：`ics-etcd:3.6.14-security.1`。导出后 Trivy HIGH/CRITICAL 门禁必须为 0。
