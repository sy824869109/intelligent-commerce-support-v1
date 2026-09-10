# contracts

保存 OpenAPI、事件合同、错误码、分页模型和跨服务 DTO。合同需要版本化，并由契约测试验证向后兼容性。

M02.3 第一批已将 E-03 的八类事件落为 `ics_contracts/events.py`，生成 `generated/browser-events-v1.schema.json`；`generated/gateway.openapi.json` 从实际网关工厂导出，仅含两条已实现健康接口。生成器检查源码与制品差异，禁止手改生成文件。

```powershell
python scripts/check_contracts.py --generate
python scripts/check_contracts.py
```

合同中的 `cursor` 是平台通知信封字段，编码时写入 SSE `id`，不重复放进 `data`；临时 delta/progress/resync 不携带持久游标。协议版本 1，未知字段/事件/版本拒绝，不猜测 KF 格式。SSE 编码器不是联网端点，不证明消息持久化或权限已验证。

第三批增加 `commerce.py`：售后申请、PAGE/CHAT 提交、服务端预检绑定、整数金额、分页和命令结果 DTO；详见 [确认与分页说明](../../docs/api/m02-3-confirmation-dtos.md)。预检内部记录不是公开响应，纯函数不是授权/事务执行器。

第四批增加 `api.py` / `routes.py`：公开投影、信封与 18 项业务路径设计，生成独立 `business-routes-v1.design.json`，不混入真实网关 OpenAPI。详见 [公开 API 设计](../../docs/api/m02-3-public-api-design.md)。字节上传、富媒体及运行鉴权仍未接入。

第五批增加 `handoff.py`、六份衔接 schema、固定响应 fixtures 与独立兼容基线，详见 [衔接与兼容说明](../../docs/api/m02-3-handoff-compatibility.md)。普通 `--generate` 不更新已审阅基线；`--init-baseline` 只允许首次创建。新增合同也须评审，不自动放行。

详见 [第一批接口与事件说明](../../docs/api/m02-3-contract-foundation.md) 和 [第二批领域事件及策略](../../docs/api/m02-3-domain-policies.md)。M02.3 整体仍在实施：上传与来源/附件读取路径、MessageContent 正式消费方式仍待冻结；尚未接入聊天、授权、发布、重放和 KF 适配器。
