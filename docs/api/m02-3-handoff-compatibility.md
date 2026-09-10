# M02.3 第五批：消息、游标、上传衔接与兼容基线

日期：2026-09-10。状态：本地验证通过，远端结果另记；M02.3 整体仍 IN_PROGRESS。

## 本批交付

| 内容 | 已实现 | 未实现 / 下一责任方 |
|---|---|---|
| 消息内容 | TEXT、SOURCE、ATTACHMENT 判别合同；来源绑定 source/version/locator 引用 | N3/N6 授权解析来源、下载附件；前端显示 |
| 分页 / 恢复游标 | 服务端记录绑定租户、用户、资源、用途、查询摘要、过期时间；纯函数校验 | N3 签发随机令牌、存储、撤销、每次读取重新授权 |
| 上传许可 | 请求大小、摘要、用途、MIME 白名单；内部许可和公开视图分离 | N3/N6 上传入口、许可消费、真实字节检查及存储 |
| 资产状态 | READY 必须具有格式/恶意内容检查通过及已验证摘要 | 实际扫描、摘要比对、权限与状态转换事务 |
| 回归基线 | 17 项 JSON 操作的固定成功响应与越权字段反例、确认摘要黄金值、路径文档交叉校验 | 后续运行端点、浏览器和多版本部署集成测试 |
| 兼容门禁 | 生成制品 SHA-256 独立基线；普通重新生成不能更新基线 | 未来变更的版本评审、迁移与消费者升级 |

另一个操作是 SSE 流，不使用 JSON 成功响应 fixture；八类事件测试沿用第一批。固定示例及严格字段检查是离线契约证据，不是业务授权或端到端成功证据。

## 数据如何流动

```text
浏览器提交上传意向（用途、字节数、MIME、内容摘要）
  ↓ 未来 N2 验证身份与目标权限
未来 N3/N6 签发 UploadPermit；浏览器仅获 UploadPermitView
  ↓ 未来上传入口受控接收字节，不能信任客户端 MIME / 摘要
隔离区 → 实际格式检查 + 恶意内容检查 + 服务端摘要比对
  ↓ 仅检查通过且权限/用途/有效期吻合，才能转换为 READY
附件引用 → MessageContent.ATTACHMENT
知识源引用 → 知识摄取任务 → 版本发布（本批未执行）
  ↓ 检索结果引用固定版本和定位信息
MessageContent.SOURCE → 未来授权解析 → 来源展示
```

- 本批 `MessageContent` 是独立内容合同，不向严格的 HTTP v1 `MessageView` 静默追加 `parts`。实际接口仍使用第四批 text + source_refs；正式富媒体读取路径/版本协商需要下一批明确。项目 V1 与协议 v1 是不同概念。
- 来源、附件引用仅是定位标识，不是访问许可；不得把存储 key、任意 URL、服务器路径或内部知识片段塞入引用字段。知识撤回、租户权限变更后，来源解析必须再次检查当前权限及发布状态。
- 游标方案选择服务端查询记录 + 不透明随机令牌，**不是已实现签名游标**。HISTORY_PAGE 和 EVENT_RESUME 不互换；查询条件变化须使用对应 query_hash。过期等于截止时刻即拒绝。跨用户、跨租户、跨资源、跨用途均拒绝；每次连接/读取还须 N2/N3 重新授权。
- 32 MiB 和四种 MIME 是本批初始工程边界，不等于已批准所有解析能力。未安装扫描器；READY 模型字段不能证明扫描执行。未来服务端必须将真实扫描结果及字节摘要与对应 upload_ref、许可和对象版本绑定，再持久化状态。
- 文件上传、MySQL 元数据和对象存储不是一个事务。未来需幂等确认、过期隔离对象清理、失败补偿、撤销后禁止新读取；本批只定义状态词汇，不声称已实现跨存储状态机。

## 版本检查的原理与限制

`scripts/check_contracts.py --generate` 仍生成确定性制品。正常检查额外对照 `packages/contracts/compatibility/v1-artifacts.sha256.json`，防止改模型后重新生成就意外放行合同变更。首次使用 `--init-baseline` 独占创建，已存在时拒绝覆盖。

这是保守的逐字节冻结，而非智能判定所有向后兼容变更。当前覆盖生成清单（包括现有健康 OpenAPI）；增加新合同或有意升级健康接口也会要求显式评审。不得仅为让 CI 变绿而更新基线。下一版本应保留旧 fixtures，记录新旧读写规则及迁移，并对基线范围作独立评审。模型语义校验不全体现在 schema 中，所以同时保留行为反例和固定响应示例。

现在只有协议 v1 的固定读取示例和未知版本拒绝测试，**没有宣称已经实现 v1/v2 双版本部署或迁移**。

## 行为与文件位置

所有路径相对于 `F:\heima\ai\python\project\i`：

- 新增 `packages/contracts/ics_contracts/handoff.py`：内容、游标、上传许可、资产校验合同和游标校验纯函数。
- 修改 `scripts/check_contracts.py`：六类新 schema 的生成、独立兼容基线检查。
- 新增 `packages/contracts/generated/` 中 message-content、cursor-binding、upload-request、upload-permit、upload-permit-view、asset-validation 六份 v1 schema。
- 新增 `packages/contracts/compatibility/v1-artifacts.sha256.json`：首次审阅快照；不是运行密钥。
- 新增 `tests/contracts/test_handoff.py`、`test_response_fixtures.py`、`test_compatibility.py`：共增加 30 项测试，部分测试内部还循环覆盖多种非法输入。
- 同步本说明、合同 README、任务台账和 CHANGELOG。
- 使用现有项目内 Python 3.12.14、Pydantic、pytest、Ruff、Bandit；没有安装或升级依赖，没有本地下载新软件。测试临时文件在 `_local_artifacts/m02-3/tmp`，Ruff 缓存在 `_local_artifacts/caches/ruff`。
- 没有数据库迁移、服务启停、Docker 数据迁移、原 KF / 原电商代码修改。GitHub push 会按既有 CI 拉取依赖和构建扫描镜像，仅在远端 runner 执行，不发布镜像、不更换本地运行镜像。

## 本地验证与下一批

`check_contracts.py`：150 passed；生成一致性、基线、Ruff、Bandit 通过。
`check_backend.py tests`：46 passed。
`ci.py`：224 项基础测试执行成功，其中 Windows 跳过 5 项符号链接测试；48 条标准引用、93 条验收记录结构有效。两项已有 Starlette/anyio 弃用警告保留，未贸然升级锁定依赖。

剩余合同工作：冻结上传许可/字节接收与来源/附件读取的路径、错误映射和授权责任；选择 MessageContent 的正式消费路径；补正反 fixtures 后完成 M02.3 最终复核。运行上传、真实鉴权、富媒体前端、知识解析仍归后续模块，不能靠增加 schema 视为完成。93 条业务验收仍 NOT_RUN，M02.4 尚未开始。
