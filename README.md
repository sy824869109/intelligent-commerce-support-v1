# intelligent-commerce-support-v1（智能电商客服平台）

这是智能电商客服平台的全新开发目录。原智能客服项目与 KF RAG 仅作为只读参考，不在原项目上继续开发。

## 当前进度

- 已完成：M00.1–M00.4、M01.1–M01.4 与 M02.1
- 当前任务：`M02.2 数据库会话、迁移与事务基础`（本地测试通过，等待最终交付门禁）
- M02.1 验收：24 项后端测试、本机 HTTP、源码/依赖审计及 GitHub Windows/Linux 门禁通过；当前健康检查仅覆盖应用自身
- 状态：新平台独立 MySQL、Redis、etcd、SeaweedFS、Milvus 全部健康；认证读写、S3/向量数据闭环、停止重启与强制重建持久化通过，本地 209 项工具单测通过。93 条业务用例仍未执行
- V1 目标：前后端、业务服务、KF RAG 知识引擎、人工工单和数据闭环在局域网内完整运行

## 开发目录

```text
F:\heima\ai\python\project\i
```

启动包保留在项目根目录，但已被 `.gitignore` 排除。只从启动包选择性提取标准文档，不解压其中的旧项目与 KF 源码作为新项目代码。

## 本地开发环境

- IDE：PyCharm 2023.2.5
- PyCharm：`F:\heima\ai\python\day01\pycharm\PyCharm\bin\pycharm64.exe`
- Conda：`F:\heima\ai\python\day01\Anaconda\Scripts\conda.exe`
- 环境名：`intelligent-commerce-support-v1`
- Python：3.12.14

创建或恢复环境：

```powershell
& 'F:\heima\ai\python\day01\Anaconda\Scripts\conda.exe' env create -f .\environment.yml
```

验证环境：

```powershell
& 'F:\heima\ai\python\day01\Anaconda\Scripts\conda.exe' run -n intelligent-commerce-support-v1 python --version
```

在 PyCharm 中打开本目录，然后选择解释器：

```text
F:\heima\ai\python\day01\Anaconda\envs\intelligent-commerce-support-v1\python.exe
```

不要提交 `.idea`、Conda 环境、模型、数据、密钥、旧项目压缩包或启动 TAR。

## 项目标准

- [M01 五服务运行方法与边界](deploy/compose/README.md)
- [M01 最终验收](docs/testing/m01-final-validation.md)
- [M01 完整行为记录](docs/operations/m01-implementation-behavior-log-20260907.md)
- [ADR-0005：自维护 Milvus 安全构建](docs/decisions/ADR-0005-maintained-milvus-security-build.md)

- [渐进式重构总控提示词](docs/baseline/00_智能电商客服平台_渐进式重构总控提示词.md)
- [V1 架构与开发方向](docs/baseline/01_智能电商客服平台_V1重构理解与初步架构.md)
- [当前技术选型](docs/baseline/02_当前技术选型基线.md)
- [不可变资产规则](docs/baseline/03_启动包说明与不可变资产规则.md)
- [只读资产台账](docs/baseline/reference-assets.md)
- [任务进度台账](docs/progress/task-ledger.md)

## 目录边界

- `apps/`：可运行应用，包括三类前端、网关、电商、会话、编排、知识、工单和 Worker。
- `packages/`：稳定共享合同、纯领域模型、可观测性和测试工具。
- `deploy/`：局域网部署资产；业务源码不能放入部署目录。
- `docs/`：架构、API、ADR、运维、测试、基线和进度文档。
- `tests/`：跨模块契约、集成、端到端、性能和安全测试。
- `scripts/`：开发期验证工具，不包含生产业务逻辑。

详细规则见 [模块边界](docs/architecture/module-boundaries.md) 和 [项目目录](docs/architecture/project-layout.md)。

## 项目治理

- [M02.1 网关运行与配置](apps/api-gateway/README.md)
- [M02.1 行为记录与新依赖位置](docs/operations/m02-1-implementation-log.md)
- [M02.1 验收记录](docs/testing/m02-1-gateway.md)
- [M02.2 数据库运行与详细行为记录](docs/operations/m02-2-database.md)
- [M02.2 验收记录](docs/testing/m02-2-database.md)

- [当前全景技术流程图：逐步讲解](docs/architecture/v1-review-20260905/V1全景技术流程图_逐步讲解.html)
- [全景图阅读说明](docs/architecture/v1-review-20260905/全景流程图_阅读说明.md)
- [流程示例走读](docs/architecture/v1-review-20260905/V1分层流程_示例走读.md)
- [V1 标准 1.1](docs/implementation-standards/v1/README.md)
- [CI 骨架说明与本地命令](docs/testing/m00-4-ci.md)

- [贡献与提交规范](CONTRIBUTING.md)
- [安全报告规则](SECURITY.md)
- [变更日志](CHANGELOG.md)
- [架构决策记录](docs/decisions/README.md)
- [版本与发布策略](docs/operations/versioning-and-release.md)
- [Definition of Done](docs/testing/definition-of-done.md)

## Git 交付原则

每个任务卡必须依次完成：代码或配置 → 测试 → 注释和文档同步 → 原子提交 → 推送 GitHub。推送失败时不得把任务标记为完成，也不得继续下一任务。
