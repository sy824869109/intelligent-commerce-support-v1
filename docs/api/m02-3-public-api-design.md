# M02.3 第四批：公开 DTO 与业务路径设计

状态：本批本地及远端验收通过；M02.3 整体仍 IN_PROGRESS。设计路径不是运行端点，实际 `gateway.openapi.json` 仍只含两条健康接口。

## 已交付

- `ics_contracts/api.py`：公开成功/错误信封、预检投影、会话/消息/人工/知识/反馈请求及结果模型。
- `ics_contracts/routes.py`：18 项操作与设计路径、请求位置、路径参数、请求/响应 schema、鉴权责任、幂等 Header、响应码的映射。
- `business-routes-v1.design.json`：生成的设计目录。其 `schemas` 中每个条目是**独立 JSON Schema 文档**，内部 `#/$defs` 应相对该条目解析，不将整个目录作为一份可执行 JSON Schema 或 OpenAPI。
- `validate_response`：离线 JSON 响应校验，检查状态码、信封和命令终态；不是 HTTP Handler，不证明领域事实已发生。
- `tests/contracts/test_api_design.py`：18 项请求正例、身份伪造拒绝、投影、错误/HTTP 映射、回执与未知结果约束。

## 设计路径

| 操作 | 方法与路径 |
|---|---|
| conversation.create | POST /api/v1/conversations |
| message.send | POST /api/v1/conversations/{conversation_id}/messages |
| conversation.snapshot | GET /api/v1/conversations/{conversation_id}/snapshot |
| conversation.events | GET /api/v1/conversations/{conversation_id}/events |
| run.cancel | POST /api/v1/conversations/{conversation_id}/runs/{run_id}/cancel |
| workflow.preflight | POST /internal/v1/workflows/{workflow_id}/preflight |
| workflow.confirm | POST /api/v1/workflows/{workflow_id}/confirmations/{confirmation_id}/submit |
| commerce.preflight | POST /api/v1/commerce/preflights |
| commerce.submit | POST /api/v1/commerce/commands |
| command.get | GET /api/v1/commerce/commands/{command_id} |
| handoff.request | POST /api/v1/conversations/{conversation_id}/handoffs |
| ticket.claim | POST /api/v1/tickets/{ticket_id}/claim |
| ticket.transfer | POST /api/v1/tickets/{ticket_id}/transfer |
| ticket.reply | POST /api/v1/tickets/{ticket_id}/replies |
| knowledge.upload | POST /api/v1/knowledge/spaces/{space_id}/sources |
| knowledge.publish | POST /api/v1/knowledge/spaces/{space_id}/publications |
| knowledge.revoke | POST /api/v1/knowledge/spaces/{space_id}/revocations |
| feedback.create | POST /api/v1/conversations/{conversation_id}/feedback |

公开路径先经过 N2；内部预检需要可验证的服务身份与委托。没有以 `/internal` 前缀代替鉴权。N4 → N5 仍调用同一领域端口，不让浏览器自行声明 CHAT 就获得服务权限。所有上述操作状态均 NOT_IMPLEMENTED。

## 数据流与字段分离

```text
HTTP Header：未来认证凭据、Idempotency-Key
路径：会话/工单/工作流等目标 ID
JSON 或 query：只放白名单业务字段
  ↓ N2 认证、目标授权、Header/路径解析（尚未实现）
本批请求模型校验
  ↓ 后续领域执行、持久化与权限复核（尚未实现）
公开 DTO / Success[data] / Failure[error]
  ↓ 离线状态码与模型一致性校验（本批已实现）
未来 HTTP 或 SSE 发送
```

- 请求体不能自报 actor_id、tenant_id、roles、confirmed 或 idempotency_key。前批 Submit 对象是内部逻辑输入，适配层未来将 Header/路径/业务 Body 组合成该输入，不把旧逻辑 DTO 直接作为 HTTP Body。
- `public_preflight` 只复制白名单字段。内部 tenant/actor、USED 状态与命令绑定不公开；订单、原因和附件引用仍须当前 actor 授权后才能展示。hash 绑定内容保持不变，不由独立自由文本摘要改写事实。
- snapshot 分页返回正式消息，message_seq 唯一递增；分页 next_cursor 和事件恢复 resume_cursor 分开，不复用序号充当游标。游标签发、租户绑定、过期和重新授权尚未实现。
- `ReplyResult.DELIVERED` 只指已保存正式消息，不表示客户已读；内部备注不进入公开 reply 请求。
- `KnowledgeUpload` 接收已授权 staging upload_ref 与内容摘要，不直接接收 URL、服务器路径或桶 key。**字节上传/上传许可合同仍待 N6 衔接**，本批没有文件上传端点，也没有病毒检查/READY 判定。
- 消息结构当前为 text + 引用的最小版本；富媒体 MessagePart、受控来源展示和附件下载协议尚待补齐，不以当前 text DTO 宣称覆盖所有聊天内容。
- KnowledgeTask 的受理/校验状态不代表可检索；KnowledgeVersionResult ACTIVE/REVOKED 只允许领域已完成后返回。本批不签发审批，不执行知识发布。

## HTTP 与版本边界

- 业务错误目录与 HTTP 状态保持对应；COMMAND_RESULT_UNKNOWN 必须使用 data，不能同时带 error。202 命令结果不允许携带 SUCCEEDED/REJECTED/FAILED 等确定终态。
- `retryable=true` 仅允许已定义的安全/同命令条件重试策略；字段本身不证明操作可重试，调用方须执行相应策略。不允许超时错误诱导盲目重做交易。
- 本批未替换 M02.1 已运行健康接口的错误模型或错误码；业务模型与当前健康兼容层明确分开。正式激活时需路由专用错误映射与测试。
- SSE 开始前可返回 HTTP Failure，开始后使用平台事件，不在半条流里追加 HTTP JSON 错误。本批仅做设计映射，不实现连接。
- Cookie/Bearer、CSRF、长连接撤权由 M03 冻结；不得将访问令牌放 URL。暂未生成带认证实现宣称的业务 OpenAPI。

## 验证与剩余工作

本地契约测试 120 项通过；新旧后端兼容与远端 CI 结果随后写入台账。复用现有锁定依赖，新增文件/缓存均在 F 盘项目内，无安装新依赖、数据库迁移、服务启停或 KF 改动。

收口前仍需：稳定黄金 fixtures/版本兼容门禁、所有响应正反例深化、MessagePart/来源引用、分页/上传许可衔接规则与设计文件交叉校验。业务运行守卫按后续模块实现，93 条业务验收仍 NOT_RUN。

## 验收证据

实现提交 `c178fb8`；[GitHub CI 34434163649](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34434163649) SUCCESS。双平台契约/后端/基础、Python 安全和四类镜像作业通过；前端与手动 Milvus 作业按既有策略 skipped，不计为本次运行通过。本地 120 项契约、46 项后端测试通过，224 项基础检查通过（Windows 跳过 5 项符号链接测试）。两项既有测试依赖弃用警告保留，未新增或升级依赖。
