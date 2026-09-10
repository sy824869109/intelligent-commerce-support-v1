# Identity

M03 租户身份、服务端会话、刷新轮换、密码策略与资源授权。数据库状态是身份和权限的来源，不信任客户端 tenant/actor/role 声明。

调用方先 authenticate，再用可信领域 loader 构造 Resource 并 authorize。权限检查不是订单/工单/知识的业务状态判断。详见 [M03 实施记录](../../docs/operations/m03-identity-acceptance.md) 和 [ADR-0009](../../docs/decisions/ADR-0009-identity-and-tenant-authority.md)。

没有默认凭据。操作员使用项目解释器执行 `scripts/bootstrap_identity.py --username admin`，交互设置首个管理员。维护端口 prune_expired 仅清理已过绝对期限会话，永不清理审计。
