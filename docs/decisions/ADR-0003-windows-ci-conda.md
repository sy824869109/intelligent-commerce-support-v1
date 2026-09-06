# ADR-0003：Windows CI 通过 Conda 保持 Python 补丁基线

- 状态：Accepted
- 日期：2026-09-06
- 关联任务：M00.4
- 取代：ADR-0002（仅修订运行时安装方式，其余 Foundation 门禁继续采用）

## 背景

首次 CI 34011147030 中 Linux 全部通过；Windows setup-python 明确报没有 3.12.14 x64 制品。不能将更低 Python 补丁当作项目同版本通过。

## 决策驱动因素

保持项目 Python 3.12.14、本地 Conda 开发习惯、双平台真实运行与隔离，不改 KF 或用户现有环境配置。

## 决策

继续采用 ADR-0002 的 Foundation 检查、只读权限、SHA/工具哈希锁、未实现作业 skipped 和激活守卫。Linux 用 setup-python；Windows 用 setup-miniconda v3.3.0 官方 SHA、固定 Miniforge 26.5.3-0 与 ci/windows-environment.yml 创建 commerce-ci 环境。conda-forge 已核验提供 win-64 Python 3.12.14，不访问需额外条款处理的 defaults 渠道。

仅两个运行时准备步骤允许按 runner.os 互斥执行；安装工具与全部实际检查均必须执行。显式 pwsh 启用 Conda 集成，CI 入口核对实际 sys.version_info，不允许激活失败后用其他 Python 通过。

## 备选方案

将 Windows 降到 3.12.10：与基线不同，不采用。移除 Windows job：丢失本地平台验证，不采用。自行编译 CPython：当前成本过高，不采用。

## 结果与影响

保留真实双平台与同补丁验证；Windows 首次需要下载 Miniforge 并解析 CI bootstrap 环境，耗时高于预装 Python。bootstrap 依赖求解与应用发布锁是不同层次，正式运行环境仍需后续独立锁定和 SBOM。

## 安全与数据影响

不修改本地 environment.yml、参考项目或 KF；不读取项目 secrets。新增 Action 用完整官方 SHA，下载来源为固定 Miniforge 发行；CI Python 工具仍用原哈希锁安装。

## 运维与回滚

保留首次失败记录及修复提交 1193aa2；新故障通过修正/revert 提交处理，不通过降级基线或跳过检查掩盖失败。

## 验证方式

本地 34 个基础测试与配置守卫通过；Windows/Linux 远端结果必须分别确认。执行记录归入 M00.4 任务台账，不把 Foundation 成功当作 93 条业务验收通过。
