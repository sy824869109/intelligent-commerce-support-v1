# M02.3 第三批：售后申请、确认、分页与结果 DTO

范围：补齐一个可验证的售后申请合同切面，不等于 18 项操作全部具备请求/响应，也不开放 HTTP 业务端点。

## 已实现结构

| 类型 | 作用与边界 |
|---|---|
| Money | 非负整数最小货币单位 + 三位大写币种代码；拒绝浮点和布尔金额。币种实际存在性及业务精度由 N5 校验 |
| Application | 仅 `after_sales.apply`；支持退货退款/仅退款/换货/维修/补发的申请类型，不代表自动退款执行 |
| ApplicationLine | 商品行与数量；1–50 行、不重复，单行数量结构上限 10000。实际剩余可申请数量须领域重新检查 |
| PreflightRecord | **服务端内部**预检记录：tenant/actor、申请、领域报价、资源/规则版本、hash、时效、状态、唯一命令引用；不是公开响应，不接受客户端整份提交 |
| PageSubmit | PAGE + preflight_id + payload_hash + 稳定幂等键；不需要虚假会话 |
| ChatSubmit | 同一预检绑定，加 confirmation_id、workflow_id/version；服务委托和确认真实性仍由 N4/N5 校验 |
| CommandResult | 分开表达权威状态、调用方观察状态、业务引用、原因与下一步；RESULT_UNKNOWN 只能为空状态或 RECONCILING，不能携带业务成功引用 |
| PageRequest / PageReferences | 不透明游标、默认 20/最大 100，has_more 与 next_cursor 一致；目前仅引用分页基础，不是完整会话快照响应 |

结构上限是防止异常输入的工程边界，不是实际商业政策。附件最多 20 个唯一受权引用，不接收文件路径或客户端身份字段。所有模型拒绝额外字段，包括 `confirmed=true`。

## 页面与聊天的共同流向

```text
申请材料 → Application 校验
  ↓ 未来 N5 授权、资源事实、规则和精确报价
服务端 PreflightRecord
  ↓ 同一结构生成可见摘要与规范化 hash
PAGE 提交引用 / CHAT 提交引用+Workflow 确认
  ↓ N2 可信身份；服务端加载原预检，不相信客户端自造记录
check_binding：身份、hash、时效、状态与稳定命令引用
  ↓ 未来 N5 当前授权/资源版本/数量/材料/确认再核验
事务绑定命令 + 申请 + 审计 + Outbox（尚未实现）
  ↓ 返回真实 CommandResult，不把 202 当退款成功
```

`check_binding` 不消耗预检，不创建命令，不完成幂等，不验证 CHAT 委托或授权权限。USED 只返回已绑定 command_id，允许失效时间之后恢复同一结果引用；调用方仍必须当前重新授权，不能据此再次执行。失效边界为 `now >= expires_at`。

## 哈希与版本约定

- 算法标签 `application-confirmation-v1`；使用 UTF-8、固定 JSON 键排序/紧凑分隔、SHA-256。
- 输入包含申请、领域计算报价、资源版本、规则版本。只排序无序商品行和附件引用，不重写原文或 Unicode，不从 LLM 文本提取金额。
- 数量、原因、报价、资源/规则版本变化必须改变 hash；确认仍需绑定原 actor/tenant/preflight。
- SHA-256 不是签名，不是授权凭据。仅比较客户端提供的两个 hash 无法证明授权；必须加载服务端可信记录。
- Pydantic frozen 不会深度冻结列表，绑定检查会重新校验快照，防止进程内列表修改绕过 hash。
- 当前规范为 Python 生产实现；前端/其他语言落地时需固定黄金向量与跨语言回归，不能假设任意 JSON 序列化完全一致。

## 文件、测试与未实现部分

- 新源码 `packages/contracts/ics_contracts/commerce.py`；新测试 `tests/contracts/test_commerce.py`。
- 新增 8 份 `*-v1.schema.json`：application、chat-submit、page-submit、command-result、money、page-request、page-references、preflight-record。模型生成，不手改。
- 校验入口仍为 `scripts/check_contracts.py`；缓存与临时文件在 F 盘项目 `_local_artifacts`，无新增依赖/服务操作，无 KF 或旧项目改动。
- JSON Schema 描述结构；跨字段 hash/状态一致性通过 Python 校验器执行，单独通过 JSON Schema 不等于全部业务规则通过。
- 仍待：其他业务完整 DTO、对外预检展示投影、完整 HTTP 错误/成功信封、正式设计路径、分页授权/签名/过期策略、跨版本 fixtures。当前 M02.3 仍 IN_PROGRESS，93 条业务验收仍 NOT_RUN。

## 验收

实现 `8ddd156` 已推送；[GitHub CI 34432601691](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34432601691) SUCCESS。双平台契约/后端/基础、Python 安全和四类镜像门禁通过；前端与手动 Milvus 作业仍按策略 skipped，不计为运行通过。本地 83 项契约、46 项后端测试通过，224 项基础检查通过（Windows 跳过 5 项符号链接测试）。两项既有测试依赖弃用警告保留，未扩展升级依赖。
