# observability

保存统一日志、脱敏、指标、追踪、关联 ID 和审计上下文适配器。业务模块只依赖这里定义的接口。

M02.4 第一批在 `ics_observability/core.py` 提供上下文隔离、固定字段诊断 JSON、固定桶指标和审计记录校验。使用标准库，暂无 exporter、持久化 sink 或网关接入；不是完整脱敏与审计系统。详见 [实施与边界](../../docs/operations/m02-4-observability-foundation.md)。

最终批已接入网关追踪/日志/指标，提供进程内 JSON 指标导出和 SQLAlchemy 同事务审计 sink。第一批“未接入”是历史状态；完整边界与验收见 [M02 收口](../../docs/operations/m02-final-acceptance.md)。不提供公共 metrics/audit 端点，不宣称跨进程追踪或防篡改归档。
