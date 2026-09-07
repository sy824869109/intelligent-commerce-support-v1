# MySQL 8.4.11 安全派生镜像

固定官方 Oracle Linux 9 基础镜像 digest，应用当前系统安全更新，移除非运行必需且存在漏洞的 MySQL Shell，并使用 Go 1.27.1 从 SHA-256 校验后的 gosu 1.19 源码重建权限切换工具。镜像仅供新平台 M01 使用，不修改原 KF。

本地准入镜像：`ics-mysql:8.4.11-security.1`。构建必须关闭 provenance/SBOM 附加清单，导出 tar 后使用仓库锁定的 Trivy 镜像扫描；HIGH/CRITICAL 必须为 0。
