# 只读参考资产台账

## 开发基线

- 开发根目录：`F:\heima\ai\python\project\i`
- 启动包：`智能电商客服重构启动包_当前稳定技术栈.tar`
- 启动包大小：`5,779,901,952` 字节
- 启动包 SHA-256：`7690AAD97C5593C3AA2791C48FD05096D723859AF75653A4A78BDEDABEB0C7AE`
- 校验日期：`2026-09-05`
- 校验结果：通过

## 启动包内参考项目

| 资产 | 大小（字节） | SHA-256 | 用途 |
|---|---:|---|---|
| `intelligentAssistant.zip` | 512,977 | `1A902066CAC9C4E3F0F508FC849F6B511A395BFA2458519C88AA6B84A68E7DF4` | 原电商客服项目精简参考 |
| `intelligentAssistant_backup_60passed.zip` | 1,286,437,846 | `C9E85DFC65B506E2F44C5240581934C691E94EAFBF6417A6928E6F8EF37B001C` | 原项目通过测试的完整备份 |
| `knowforge-rag-platform.zip` | 4,492,887,820 | `17B87DC3E0EAAF8DFFF6FEC4F9B23C2EDF734128B38CABC4281F9DE659FE967F` | KF RAG 核心架构参考 |

三个参考项目没有解压到新项目代码区，也不得提交 GitHub。需要分析时使用临时只读目录或原始只读位置；分析结束后不向参考源写入内容。

## 不可变规则

1. 原项目只提供业务需求、场景、领域规则和测试参考。
2. KF RAG 提供知识引擎核心分层、职责与链路标准。
3. 新平台必须在当前开发目录从零建设。
4. 不修改三个参考压缩包，不在其解压目录中开发。
5. 引用资产的 SHA-256 变化时立即停止开发并定位原因。
6. 大型压缩包、模型、知识文件和运行数据不进入 Git。

## 本地工具

| 工具 | 路径/版本 | 使用边界 |
|---|---|---|
| Conda | `F:\heima\ai\python\day01\Anaconda` / 24.5.0 | 为新平台创建独立环境，不修改 `kfRag` 环境 |
| PyCharm | `F:\heima\ai\python\day01\pycharm\PyCharm` / 2023.2.5 | 打开当前开发根目录，项目解释器选择新 Conda 环境 |
