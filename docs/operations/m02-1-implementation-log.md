# M02.1 实施行为记录

日期：2026-09-08。范围：网关应用工厂、健康与错误响应、关联日志、后端质量门禁。

交付结果：M02.1 已完成，实施提交 `acc5fb3` 已推送至 `codex/v1-greenfield`。
[远端验收运行 34187050206](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34187050206) 全部必需作业通过。
随后仅同步 README、台账、验收、行为记录与变更日志的完成状态；不提前实施 M02.2。

## 写入文件与作用

- apps/api-gateway/ics_gateway：settings 配置边界、responses 返回结构、middleware 请求关联/脱敏日志、app 应用与生命周期。
- apps/api-gateway/requirements.in、requirements.lock：运行直接依赖与含传递依赖的 wheel 哈希锁。
- ci/backend-requirements.in、backend-requirements.lock：后端测试、Bandit、pip-audit 与工具完整锁。
- scripts/run_gateway.py：本机启动；scripts/check_backend.py：真实测试和安全审计入口。
- tests/backend：HTTP/配置/隔离/失败行为回归；tests/unit/test_foundation.py：CI 激活规则回归。
- .github 工作流与阶段清单、scripts/verify_ci.py、scripts/ci.py：激活后端与安全门禁，保留其他阶段状态。
- 本记录、API 说明、ADR-0006、验收记录、README、Makefile、变更日志和台账同步阶段进度。

## 下载 安装及路径

新增 Conda prefix：`F:\heima\ai\python\project\i\_local_artifacts\dependencies\platform`。
解释器：该目录 `python.exe`，Python 3.12.14。已有 F 盘 Anaconda 仅用来创建新 prefix。
Conda 下载缓存：`_local_artifacts/caches/conda`，初始安装计划约 34.2 MB，包括 Python、pip、
OpenSSL、SQLite、运行库等。实际安装包记录见新环境 `conda-meta`。
pip 缓存：`_local_artifacts/caches/pip`；临时目录：`_local_artifacts/m02-1/tmp`。
完整解析报告和 PyPI 包元数据：`_local_artifacts/m02-1`。

首次 runtime dry-run 沿用电脑已有清华镜像地址；后续解析/安装显式使用官方 PyPI。
安装文件以 canonical PyPI 的 wheel SHA-256 核验。没有更新已有 Conda 环境、系统 PATH 或 Docker 设置。
pip 解析报告保留下载 URL/哈希/包大小；Git 内锁文件提供最终完整版本清单，不写入凭据。

## 运行及数据行为

网关只读环境变量，默认不读取磁盘 .env 或任何 M01 secrets。当前无数据库连接、写表、对象上传、
向量写入或调用模型行为。就绪扩展测试使用注入的合成 callback；测试中的异常/参数端点仅定义在测试文件。
真实本机冒烟只访问本次启动的 127.0.0.1:28000 健康、文档及未知路径；不会执行基础设施启停或重建。
Docker 既有数据保持原位。运行日志只写项目内 `_local_artifacts/m02-1`。

## 开发启动与测试

在项目根目录执行。PyCharm 选新 prefix 的 python.exe，工作目录设项目根目录。

```powershell
$env:PIP_CACHE_DIR="$PWD\_local_artifacts\caches\pip"
$env:TEMP="$PWD\_local_artifacts\m02-1\tmp"
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
& .\_local_artifacts\dependencies\platform\python.exe -m pip install --index-url https://pypi.org/simple --require-hashes --only-binary=:all: -r apps/api-gateway/requirements.lock -r ci/backend-requirements.lock
& .\_local_artifacts\dependencies\platform\python.exe scripts/check_backend.py tests
& .\_local_artifacts\dependencies\platform\python.exe scripts/check_backend.py security
& .\_local_artifacts\dependencies\platform\python.exe scripts/run_gateway.py
```

只运行一个实例；终端 Ctrl+C 触发 lifespan 关闭。生产认证、数据库会话、流式协议、完整日志追踪与
局域网入口均为后续任务。最终验证及 Git 提交由 [验收记录](../testing/m02-1-gateway.md) 和 Git 历史追溯。

## 实施中发现与修正

1. 依赖解析不能把尚未哈希锁定的 .in 与已有哈希锁混装做 dry-run，否则 pip 自动启用
   require-hashes 并拒绝缺哈希的包。改为先独立解析全部直接版本，再按官方 wheel 元数据生成完整锁。
2. 工作流单行 `--only-binary=:all:` 含 YAML 冒号，必须引用完整字符串；本地 YAML 门禁发现后修正。
3. 新 ADR 按仓库模板补齐背景、驱动因素、备选、影响、安全、回滚和验证章节。
4. 旧 CI 测试固定要求所有应用阶段 skipped，已更新为后端/安全 ACTIVE，前端/机器合同仍 skipped；
   镜像测试补入 M02.1 所需合成文件 fixture，保留防假成功验证。
5. pip-audit 不识别假定的 PIP_AUDIT_CACHE_DIR，初次审计在 C 盘自动生成 67 个临时缓存文件。
   已改为显式 --cache-dir 指向项目 `_local_artifacts/caches/pip-audit`，复扫通过且无缓存写入警告。
   只针对本轮新文件尝试迁移，因 Windows 加密属性失败；后续精确清理被自动安全检查拦截。
   原 C 盘临时缓存保留待处理（67 个文件，共 605,910 字节，位于 C:\Users\111\AppData\Local\pip-audit\Cache），不声称已经清空；既有 Docker 数据和旧依赖没有迁移或删除。

本轮后台启动网关供本机审查，创建时 PID 为 27980。日志位于 `_local_artifacts/m02-1/gateway.stdout.log`
和 `gateway.stderr.log`；可先核对进程命令行再停止该实例，不应按 Python 程序名全局停止。
