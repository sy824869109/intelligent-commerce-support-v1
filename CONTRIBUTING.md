# 贡献规范

## 开发前提

1. 开发根目录为 `F:\heima\ai\python\project\i`，本地 IDE 使用 PyCharm。
2. Python 命令使用 Conda 环境 `intelligent-commerce-support-v1`。
3. 旧电商项目、KF RAG、模型、知识文件和启动 TAR 都是只读或本地资产，不进入 Git。
4. 开始任务前确认工作区干净，并同步远端开发分支。

## 一次只完成一张任务卡

每张任务卡按以下顺序执行：

1. 从 `docs/progress/task-ledger.md` 确认当前任务及前置条件。
2. 只修改当前任务范围内的代码、测试、迁移、注释和文档。
3. 运行模块测试、结构检查、静态检查和相关回归。
4. 检查差异中不存在密钥、隐私数据、模型、大型压缩包或无关改动。
5. 创建一个原子提交并立即推送 GitHub 开发分支。
6. 推送成功后才更新任务为 `DONE`，再提交和推送完成记录。

## 分支

- `main`：可发布分支，不直接开发、不强制推送。
- `codex/v1-greenfield`：V1 集成分支。
- `codex/v1-<module>`：仅在高风险或多人并行模块需要隔离时创建。
- 阶段合并通过 Pull Request 完成；删除远端分支前确认提交已合并。

## 提交信息

使用 Conventional Commits：

```text
<type>(<scope>): <imperative summary>
```

允许的常用类型：`feat`、`fix`、`refactor`、`test`、`docs`、`chore`、`build`、`ci`、`perf`、`security`。

示例：

```text
feat(order): add authorized order detail query
test(rag): cover citation and abstention behavior
docs(progress): mark M00.3 complete
```

禁止把格式化全仓、依赖升级和业务功能混在一个提交中。

## 代码和注释

- 文件、类型、函数和变量使用清晰英文；团队文档和业务规则注释使用中文。
- 注释解释原因、边界和风险，不逐行翻译代码。
- 行为改变时，在同一个提交更新注释、API、迁移和文档。
- 公共接口、状态机、检索策略、安全规则和复杂查询必须有 docstring/JSDoc。
- `TODO` 必须包含任务编号或明确退出条件。

## Pull Request

PR 必须说明范围、测试证据、架构影响、数据迁移、安全影响、回滚方式和未解决风险。CI 未通过、存在未处理审查意见或没有回滚说明时不得合并。

## 禁止操作

- 禁止 `push --force` 到共享分支。
- 禁止提交真实 `.env`、密钥、Token、用户数据、日志、模型权重和大型归档。
- 禁止直接修改他人服务拥有的数据表。
- 禁止修改旧项目或 KF RAG 参考源。
- 禁止跳过失败测试或用占位实现冒充任务完成。
