# orchestration-service

确定性对话编排与业务路由中心。

- 负责：意图、风险、澄清、多轮状态机、路由优先级和可审计决策理由。
- 依赖：通过端口调用 commerce、knowledge、ticket 和 conversation 服务。
- 禁止：让模型覆盖人工优先、安全规则、权限规则或业务状态机。
- 首次实现：M08.1。
