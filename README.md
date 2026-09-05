# intelligent-commerce-support-v1（智能电商客服平台）

这是智能电商客服平台的全新开发目录。原智能客服项目与 KF RAG 仅作为只读参考，不在原项目上继续开发。

## 当前进度

- 当前任务：`M00.1 开发基线初始化`
- 状态：本地基线与 Conda 环境已验证，等待 GitHub 远端配置后完成首次推送
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

- [渐进式重构总控提示词](docs/baseline/00_智能电商客服平台_渐进式重构总控提示词.md)
- [V1 架构与开发方向](docs/baseline/01_智能电商客服平台_V1重构理解与初步架构.md)
- [当前技术选型](docs/baseline/02_当前技术选型基线.md)
- [不可变资产规则](docs/baseline/03_启动包说明与不可变资产规则.md)
- [只读资产台账](docs/baseline/reference-assets.md)
- [任务进度台账](docs/progress/task-ledger.md)

## Git 交付原则

每个任务卡必须依次完成：代码或配置 → 测试 → 注释和文档同步 → 原子提交 → 推送 GitHub。推送失败时不得把任务标记为完成，也不得继续下一任务。
