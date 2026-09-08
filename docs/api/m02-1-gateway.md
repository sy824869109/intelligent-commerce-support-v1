# M02.1 网关 HTTP 基线

本阶段只有网关健康与文档端点，无电商业务接口和身份授权能力。服务默认只监听 `127.0.0.1:28000`。

| 接口 | 正常结果 | 异常结果 |
|---|---|---|
| GET /health/live | 200，data.status=alive | 进程停止则连接失败 |
| GET /health/ready | 200，data.status=ready | 503 SERVICE_NOT_READY |
| GET /docs | 开发 Swagger UI HTML | 关闭 docs 后 404 |
| GET /openapi.json | 自动生成的 OpenAPI | 关闭 docs 后 404 |

健康响应示例（示例 ID 为虚构）：

```json
{"request_id":"example-request","trace_id":"server-generated-id","data":{"status":"ready","service":"api-gateway","scope":"application","checks":{"lifecycle":"ok"}}}
```

成功响应只含 request_id、trace_id、data；错误响应只含 request_id、trace_id、error。
error 字段包含 code、message、retryable、client_action、command_id；本阶段 command_id 为 null。
健康接口中的 scope=application 非常重要：M02.1 不检查业务数据库、RAG、模型或前端就绪。

| 错误码 | HTTP | 客户端行为 |
|---|---:|---|
| NOT_FOUND | 404 | 核对路径 |
| METHOD_NOT_ALLOWED | 405 | 使用 Allow 中的支持方法 |
| VALIDATION_ERROR | 422 | 修正输入，不返回原始输入值 |
| UNAUTHORIZED / FORBIDDEN | 401 / 403 | 为后续真实授权错误预留映射，不代表已实现登录 |
| SERVICE_NOT_READY | 503 | 只读健康请求可退避重试 |
| INTERNAL_ERROR | 500 | 持请求 ID 排障，不默认重试业务写入 |

X-Request-ID 仅接受一个 ASCII 字母/数字起始、随后字母数字或 `._-`、总长 1–64 的值；
重复、非法或缺失时由服务端生成 UUID hex。X-Trace-ID 总由服务端生成，当前仅为诊断关联标识，
不宣称 W3C traceparent 传播或 OpenTelemetry 已接入。两类 ID 均不构成身份、租户或权限。

所有 HTTP 返回附带 X-Request-ID、X-Trace-ID、Cache-Control: no-store 和 nosniff。
JSON 请求日志仅记录方法、路由模板、状态、耗时和两个 ID；不记录 body、query、Authorization、
任意异常详情或未知请求路径。意外错误在响应开始前统一为脱敏 500；流已开始则中止并记录失败，
不会在半截响应中拼接第二个成功/失败 JSON。SSE/WS 业务协议属于 M02.3 后的实施范围。

参考：[FastAPI 应用生命周期](https://fastapi.tiangolo.com/advanced/events/)。
框架自动生成的基础健康 OpenAPI 不等于已经冻结 packages/contracts 的业务与事件合同。
