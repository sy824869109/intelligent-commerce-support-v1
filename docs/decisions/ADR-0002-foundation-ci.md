# ADR-0002：基础 CI 与渐进激活门禁

- 状态：Accepted
- 日期：2026-09-06
- 决策者：项目实施（按用户批准 M00.4 范围）
- 关联任务：M00.4

## 背景

当前仅有骨架、治理与标准；需要真实 CI，但没有应用代码、机器合同或 Dockerfile，不能把占位测试宣称为通过。

## 决策驱动因素

本地 Windows Conda 与 Linux 部署的一致性；最少权限、可复现工具、正反例测试和真实完成状态；KF 依赖与原始参考保持不变。

## 决策

使用 GitHub-hosted ubuntu-24.04/windows-2022 和项目 Python 基线；Foundation 执行结构、治理、标准、Ruff、AST、仓库安全模式及 unittest。占位 job 保持 skipped，新增应用输入即要求激活相应实际检查。

CI 专属工具 Ruff 0.16.6（MIT）、PyYAML 6.0.3（MIT）取官方 PyPI 固定发行与哈希；不引入应用依赖。Action 选 checkout v6.0.2、setup-python v6.2.0 官方提交 SHA，不跟随新主版本。依赖许可证与来源以发行元数据为准，后续 SBOM 汇总。

## 备选方案

远端实测补充：Windows setup-python 缺少 Python 3.12.14 制品。Windows 改用 SHA 锁定 setup-miniconda v3.3.0 + Miniforge 26.5.3-0 + conda-forge 的同补丁 Python；CI 入口核对实际版本。Linux 仍用 setup-python。不降级项目 Python、不更改用户 Conda 环境配置。

立即生成空 FastAPI/Vue 与假 Docker 镜像：越过 M02/M14/M18，且绿色结果误导，不采用。现在就引入完整应用 SAST/运行测试：没有受测模块，先显式占位，在第一份运行源码/合同引入时同步启用。

## 结果与影响

获得可以真实运行的最小 CI；后续新增模块会故意触发激活守卫，必须补真实 job 及测试。工具增加少量下载成本，网络与 runner 不可用时不能宣称完成。仓库模式扫描不等于完整安全审计。

## 安全与数据影响

只读 GITHUB_TOKEN、禁持久 checkout 凭据、不使用 pull_request_target/self-hosted；不传项目 secrets、不发布镜像。安全扫描只读 Git 跟踪文件，不读取个人归档/运行数据，报告不输出命中秘密。

## 运维与回滚

同一命令 `python scripts/ci.py` 在本地和 CI 运行；工具版本/hash 单独锁定。故障通过修正或 revert 提交恢复，不强推、不偷偷跳过门禁。

## 验证方式

本地运行全部正反例，确认空测试/违规配置/危险跟踪资产被拒；推送后分别查看 Windows/Linux job。远端失败时 M00.4 保持 IN_PROGRESS。没有执行的业务验收继续 NOT_RUN。
