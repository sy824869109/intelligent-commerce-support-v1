# conversation-service

会话和消息事实服务。

- 负责：会话、消息、消息片段、附件、上下文摘要、流式事件、幂等和用户反馈。
- 拥有数据：Conversation、Message、Attachment、Feedback 及相关 Outbox。
- 禁止：自行决定订单、RAG 或人工路由结果。
- 首次实现：M07.1。
