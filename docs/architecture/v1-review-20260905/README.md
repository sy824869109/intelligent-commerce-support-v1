# V1 构建与数据流审查

文档日期：2026-09-05。技术状态基于提交 `55225c9`：M00.1 至 M00.3 完成，M00.4 与业务模块尚待建设。本次只增加审查材料，不推进实现任务状态。

## 阅读顺序

1. Word 第 1 页：总体架构与局域网入口。
2. 第 2 页：节点职责、输入输出、数据所有权及返回链路。
3. 第 3 页：KF 原有 Stage 0 至 7 与旁路。
4. 第 4 页：知识入库、版本发布、反馈与纠错闭环。
5. 第 5 页：构建阶段与业务、故障验收结果。

`V1项目架构图.html` 可直接在浏览器打开，不访问 CDN。页面内含三张 SVG；切换大图或使用浏览器缩放可逐个检查箭头。独立 SVG 可编辑，PNG 可用于汇报。

## 口径

- 三端与七个后端/Worker 目录代表逻辑边界，V1 可合并低负载业务模块部署。
- IAM 作为权限子模块列出，不表示已新增独立服务。N9 是全局可观测性能力。
- 各处 MySQL 标注表示逻辑所有权，可共用实例；领域模块只写自有数据。
- N3 持有正式会话，N4 持有编排状态，N5 持有商务/售后事实，N7 持有人工工单。
- Bad Case 建议归 N6 外层治理子模块保存和审核，具体归属待 M13 契约确定；不修改 KF 内部 Pipeline。
- KF 原有直答、FAQ 直出、证据不足及 Stage 0 至 7 顺序保留。图示为正常主路和主要旁路，错误事件统一由平台记录失败状态。
- V1 的支付、订单等以查询和受控申请为主，模型不自动执行资金动作。真实渠道接入与演示数据分别验收。

## 依据

- `docs/baseline/00_智能电商客服平台_渐进式重构总控提示词.md`
- `docs/baseline/01_智能电商客服平台_V1重构理解与初步架构.md`
- `docs/architecture/module-boundaries.md`
- `docs/decisions/ADR-0001-modular-monorepo-and-kf-boundary.md`
- `docs/progress/task-ledger.md`
- KF 只读参考目录中的 `qa_core/application/service.py`、`qa_core/pipeline/rag.py`、`qa_core/pipeline/retrieval_steps.py` 和 `qa_core/pipeline/__init__.py`。

## 文档验证

Word 共 5 页，使用本机 Word 16 导出并通过运行时 Poppler 逐页渲染核查。已检查分页、表格、中文显示、标题和图中连线。渲染中间件不作为项目交付内容；未修改两套参考项目或其压缩包。
