# contracts

保存 OpenAPI、事件合同、错误码、分页模型和跨服务 DTO。合同需要版本化，并由契约测试验证向后兼容性。

M02.3 起将 [接口事件与恢复标准](../../docs/implementation-standards/v1/03_接口事件_幂等与失败恢复.md) 落为机器合同，并联动 [会话与接管规则](../../docs/implementation-standards/v1/01_会话状态_打断与人工接管.md) 和 [业务确认规则](../../docs/implementation-standards/v1/02_混合业务决策_用户确认.md)。本次只增加实施依据，不提前创建或宣称已有 OpenAPI 实现。
