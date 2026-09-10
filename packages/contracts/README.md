# contracts

保存 OpenAPI、事件合同、错误码、分页模型和跨服务 DTO。合同需要版本化，并由契约测试验证向后兼容性。

M02.3 第一批已将 E-03 的八类事件落为 `ics_contracts/events.py`，生成 `generated/browser-events-v1.schema.json`；`generated/gateway.openapi.json` 从实际网关工厂导出，仅含两条已实现健康接口。生成器检查源码与制品差异，禁止手改生成文件。

```powershell
python scripts/check_contracts.py --generate
python scripts/check_contracts.py
```

合同中的 `cursor` 是平台通知信封字段，编码时写入 SSE `id`，不重复放进 `data`；临时 delta/progress/resync 不携带持久游标。协议版本 1，未知字段/事件/版本拒绝，不猜测 KF 格式。SSE 编码器不是联网端点，不证明消息持久化或权限已验证。

详见 [第一批接口与事件说明](../../docs/api/m02-3-contract-foundation.md)。M02.3 整体仍在实施：业务操作 DTO、领域事件信封、错误目录及完整兼容策略随后补齐；尚未接入聊天、授权、发布、重放和 KF 适配器。
