# CI 范围：基础检查与新平台存储依赖镜像

`foundation` 保持 Ubuntu 24.04 / Windows 2022 双平台、15 分钟上限和原有基础检查。
M01 仅将 `image-build` 激活为真实任务，不能将其解读为业务应用已完成。

## 已激活的 image-build

1. 等待基础检查成功，使用锁定 SHA 的 Checkout，禁止持久化 GitHub 凭据。
2. 在 Ubuntu 24.04 构建 `deploy/images/seaweedfs/Dockerfile`；构建上下文只包含该依赖配方目录，不包含仓库根目录、本地凭据或旧 KF。
3. 将 `ics-seaweedfs:ci` 导出为 runner 临时目录内的 Docker 镜像归档。
4. 使用精确版本与 digest 锁定的 Trivy 0.74.0 扫描归档。任意 HIGH/CRITICAL 漏洞、扫描错误或超时均使任务失败；不忽略未修复漏洞。

扫描器非 root 运行、根文件系统只读、无额外 Linux capabilities；只读挂载镜像归档目录，不挂 Docker socket、仓库或本地 secrets。漏洞数据库允许在线更新；固定扫描器版本不意味着固定或过时的漏洞情报。

镜像任务总上限为 45 分钟，其中扫描命令另有限时。构建并行度在受审配方中限制。
此任务不启动存储服务，不验证 S3/Milvus 数据契约，不推送镜像，也不增加 GitHub token 权限。

## 仍未实现的任务

`backend`、`frontend`、`contracts`、`security-audit` 继续保留 `NOT_IMPLEMENTED` 与显式跳过状态。
应用 SAST/依赖审计没有因这一次存储镜像漏洞扫描而宣称完成；93 项业务验收仍需独立执行。

`.github/ci-stages.json` 保留原有全部 Dockerfile 检测规则，只登记这一份受审镜像输入。
新增任何应用或其他依赖 Dockerfile 都会触发守卫失败，必须补充真实构建/扫描与新的评审，不能缩窄 markers 绕过。

`scripts/verify_ci.py` 校验实际命令、扫描器锁定、只读归档边界、失败传播和权限；
`tests/unit/test_ci_image.py` 的负向用例验证这些守卫，单元测试通过不等于镜像构建或漏洞扫描已经通过。
