# Redis 8.8.2 安全派生镜像

固定官方 Alpine 3.23 镜像 digest，并将 `libcrypto3`、`libssl3`、`setpriv` 锁定到已验证的修复版本。镜像仅供新平台 M01 使用，不修改原 KF。

本地准入镜像：`ics-redis:8.8.2-security.1`。导出后 Trivy HIGH/CRITICAL 门禁必须为 0。
