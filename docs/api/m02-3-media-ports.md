# M02.3 第六批：媒体端口与收口复核

日期：2026-09-10。接口均为 DESIGN_ONLY / NOT_IMPLEMENTED，不是已运行 HTTP 服务。

## 新增端口

| 操作 | 路径 | 成功结果 |
|---|---|---|
| upload.permit | POST /api/v1/uploads | 201 上传许可 |
| upload.bytes | PUT /api/v1/uploads/{upload_ref}/bytes | 202 VALIDATING |
| upload.get | GET /api/v1/uploads/{upload_ref} | 200 当前校验状态 |
| message.content | GET /api/v1/conversations/{conversation_id}/messages/{message_id}/content | 200 MessageContent |
| message.source | GET /api/v1/conversations/{conversation_id}/messages/{message_id}/sources/{source_ref}/versions/{version_ref}/locators/{locator_ref} | 200 受控纯文本来源 |
| message.attachment | GET /api/v1/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_ref}/bytes | 200 二进制附件 |

JSON 成功统一使用 request_id / trace_id / data；二进制下载不是 JSON。所有 ID 使用既有不透明标识规则。GET 不携带 JSON Body；Empty 表示不接受额外 query 参数。新路径没有访问令牌参数；M03 冻结认证载体、CSRF 与撤权策略后才可激活。

## 示例链路

客户在 C1 会话上传图片：

1. POST uploads，提交 file（CHAT_ATTACHMENT、字节数、SHA-256、image/png）及 target（CONVERSATION、C1）。服务端核对用户、租户、会话权限和配额，使用 Idempotency-Key 去重，返回 U1 许可及期限。
2. PUT U1/bytes，Content-Type 为 application/octet-stream，Content-Length 必须与许可字节数相同。服务端边接收边限制总量并计算摘要，完整字节符合许可后才返回 202 VALIDATING。不是 READY，更不能直接发起知识发布。
3. GET U1 查询。真实格式/恶意内容检查通过后，聊天上传返回 READY、attachment_ref=A1、verified_sha256。知识上传不生成聊天附件引用，仍以 upload_ref 交给已有 knowledge.upload 操作。
4. 原 message.send 提交 attachment_refs=[A1]；正式消息落库后，snapshot 继续使用旧结构，前端按 message_id 调用新增 content 获取 TEXT / SOURCE / ATTACHMENT。临时 token 不能替代正式消息。
5. 用户点击 A1，经 C1/M1/A1 路径读取；服务端再次核对 C1、M1、A1 的实际关系、租户和当前 READY 状态，返回受控下载字节。
6. 点击知识来源，则通过消息中已存在的 source/version/locator 三元组读取；服务端同时检查引用属于该正式消息、知识版本仍可见且当前用户有权限。不可通过改路径读取未引用的片段。

## 运行实施必须遵守的规则

- **许可绑定**：服务端持久化租户、发起用户、完整 target、用途、大小、摘要、期限、对象版本和状态；旧 UploadPermit 单独不足以承载 target，不可直接当完整数据库记录。客户端无法自报 tenant/actor/扫描结果。公开许可不返回桶 key 或可绕过权限的 URL。
- **权限分工**：N2 认证；N3 管聊天附件及消息关系；N6 管知识空间上传与来源发布可见性。目标权限在许可签发、字节接收、引用消费和读取时复核。来源说明可能含敏感信息，必须授权后按最小片段返回。
- **幂等**：签发许可按租户/用户/操作/target/key 绑定请求摘要。字节 PUT 按同一许可、同一摘要处理，并发条件写不能替换现有对象；不同内容返回 UPLOAD_CONFLICT。接收超时先 GET U1，不盲目新建许可。已经 VALIDATING 的同内容重试可返回 202；已经 READY 的重试返回冲突并要求 GET，以免把完成状态写回 VALIDATING。
- **大小与类型**：本版 32 MiB 上限。超过上限返回 413；类型不支持返回 415；长度/摘要不一致返回 422。缺少 Content-Length 返回 422；不接受压缩 Content-Encoding，不支持分块续传或多部分上传。必须实际流式计数，不能只信 Header。扫描失败保持 REJECTED，不发放可读引用。
- **跨存储失败**：上传先入隔离区，摘要与扫描结果绑定实际对象版本，再以条件更新转 READY。重试复用任务/对象标识；孤儿清理只针对本平台、期限到期且无活动引用的对象。删除/撤销状态不允许新下载；不得把对象上传与 MySQL 写入声称为单个原子事务。
- **读取安全**：SourceView.title/excerpt 作为纯文本渲染，不使用原始 HTML。下载强制 application/octet-stream、Content-Disposition: attachment（服务端生成安全文件名）、X-Content-Type-Options: nosniff、Cache-Control: private, no-store；来源/内容 JSON 同样 no-store。不直接重定向对象存储，不支持 Range，整对象下载有界。响应中途失败关闭连接，不拼接 JSON 错误。
- **恢复与撤销**：过期许可拒绝新字节，已接受的后台校验仍可完成；查询需当前授权。权限或发布状态变更后不允许新的读取，不能保证追回用户此前已经下载的内容。运行端设置连接期限及撤权取消机制，具体预算归 M17，不假称离线模型已执行中断。

## 错误映射

新媒体扩展使用独立 MediaFailure，不修改旧 Failure 枚举。各错误只允许绑定的 HTTP 状态；不存在客户端自由声明 retryable。

| 错误 | HTTP | 调用方行为 |
|---|---|---|
| AUTH_REQUIRED | 401 | 重新认证 |
| ACCESS_DENIED | 404 | 停止，统一隐藏不存在/无权访问的资源 |
| INPUT_INVALID | 422 | 修正字段、长度或摘要 |
| UPLOAD_EXPIRED | 410 | 已确认过期后重新申请许可 |
| UPLOAD_CONFLICT | 409 | 查询同一许可，不覆盖内容 |
| ASSET_NOT_READY | 409 | 查询状态；拒绝/撤销/删除时停止，不无限轮询 |
| PAYLOAD_TOO_LARGE | 413 | 缩小文件 |
| MEDIA_UNSUPPORTED | 415 | 使用允许的类型/编码 |
| RATE_LIMITED | 429 | 按 Retry-After 有界退避；写操作保留身份 |
| UPSTREAM_UNAVAILABLE | 503 | 读操作有界重试；写操作先查询同一许可 |

错误在认证与资源授权之后细分，避免借过期/冲突错误枚举其他用户的上传。二进制响应开始前使用 JSON MediaFailure，开始后只能结束连接。网关尚未安装上述映射。

## 兼容性评审

本批新增独立 media-routes-v1.design.json，原 18 项设计路径及原有生成文件逐字节不变。MessageContent 通过新增读取端点消费，不向旧 snapshot 增加严格客户端未知的字段。

扩展审核采用 `--init-media-extension` 独占创建 v1-media-extension.sha256.json，只接受新增制品；原基线不能改变、扩展不能覆盖原条目。普通 --generate 不审批任何变更。CI 同时校验原基线和扩展。该命令为当前媒体扩展专用，不自动批准今后的任意新版本。

## 行为记录与复核结论

新增 media.py、test_media.py、媒体设计 JSON、扩展摘要基线和本文；修改生成/兼容脚本、合同 README、CHANGELOG 和任务台账。全部位于 F:\heima\ai\python\project\i，复用项目内 Python/Pydantic/pytest/Ruff/Bandit，未安装或升级依赖。缓存与临时测试文件继续使用项目 _local_artifacts 下既定目录。

未修改 KF、原电商项目、既有数据库或 Docker 数据；未启动上传、下载、扫描、消息或知识业务接口。GitHub 按既有 CI 在远端下载构建依赖和扫描镜像，不部署到本机。

合同层的此前缺口已明确：富媒体消费路径、上传许可/字节/状态、来源和附件读取、失败映射和权限责任均有对应设计。最终收口仍需本批本地完整检查及远端 CI 通过；运行闭环不能用合同测试替代，93 条业务验收保持 NOT_RUN。M02.4 为下一实施任务（日志、trace、metric、审计基础库），本批不提前执行。

本地验收：169 项契约测试、46 项后端测试通过；224 项基础测试运行成功（Windows 跳过 5 项符号链接测试）。生成一致性、原基线与媒体扩展基线、Ruff、Bandit、结构与治理检查均通过。两项既有测试依赖弃用警告保留。远端 CI 尚待本次推送后确认，不提前记录为成功。

最终确认：实现 `694b5f4` 的 [GitHub CI 34447200294](https://github.com/sy824869109/intelligent-commerce-support-v1/actions/runs/34447200294) SUCCESS。M02.3 合同阶段收口，以上“待确认”为历史记录；不代表实际媒体服务或业务验收完成。
