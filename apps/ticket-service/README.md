# ticket-service

人工工单与客服协作服务。

- 负责：工单、队列、分配、认领、转派、升级、内部备注、SLA、关闭和重开。
- 拥有数据：Ticket、Assignment、InternalNote、Tag、SLA 及审计事件。
- 禁止：人工纠错覆盖原始会话；纠错必须作为可追溯的新记录保存。
- 首次实现：M12.1。
