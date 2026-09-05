"""Generate the supplemental V1 flowchart; no reference or application code is touched.

The diagram describes the reviewed target, not implemented services. Resource IDs
are local cross-references, not extra sequential steps or direct database grants.
Run with Python 3.12+; the sibling browser script renders and checks the result.
"""

from html import escape
from pathlib import Path


OUT = Path(__file__).resolve().parents[1]
STEM = "05_平台端到端详细流程"
WIDTH, HEIGHT = 2000, 5260
BG, PANEL, INK, MUTED = "#0c1524", "#101e30", "#eef6ff", "#a7bbd0"
CYAN, GOLD, GREEN, PURPLE = "#67cce5", "#f0ba54", "#69d6b0", "#bda3ff"
layers = {key: [] for key in ("groups", "edges", "nodes", "labels")}


def put(layer, content):
    layers[layer].append(content)


def text(x, y, value, size=20, color=INK, weight=400, anchor="middle", layer="nodes"):
    put(layer, f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
        f'font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>')


def group(key, x, y, w, h, title, subtitle="", color=CYAN):
    put("groups", f'<g id="{key}"><rect x="{x}" y="{y}" width="{w}" height="{h}" '
        f'rx="14" fill="{PANEL}" fill-opacity=".88" stroke="#2b4059" stroke-width="2"/>')
    text(x + 25, y + 36, title, 25, color, 700, "start", "groups")
    if subtitle:
        text(x + w - 25, y + 35, subtitle, 18, MUTED, 400, "end", "groups")
    put("groups", "</g>")


def box(key, x, y, w, h, title, lines=(), color=CYAN, size=20, emphasis=False):
    # Each node owns its text so browser QA can verify both containment and clipping.
    put("nodes", f'<g id="{key}" class="node" data-box="{x},{y},{w},{h}">'
        f'<title>{escape(title + "；" + "；".join(lines))}</title>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" '
        f'fill="{PANEL}" stroke="{color}" stroke-width="{3 if emphasis else 1.8}"'
        f'{" filter=\"url(#glow)\"" if emphasis else ""}/>'
        f'<rect x="{x}" y="{y + 15}" width="4" height="{h - 30}" rx="2" fill="{color}"/>')
    total = 29 + 28 * len(lines)
    baseline = y + (h - total) / 2 + 23
    text(x + w / 2, baseline, title, 23, color, 700)
    for i, line in enumerate(lines):
        text(x + w / 2, baseline + 31 + i * 28, line, size)
    put("nodes", "</g>")


def edge(points, label="", lx=None, ly=None, dashed=False, color=CYAN, arrow=True):
    coords = " ".join(("M" if i == 0 else "L") + f"{x},{y}" for i, (x, y) in enumerate(points))
    # Round joins keep elbow routing legible without introducing ambiguous crossings.
    put("edges", f'<path class="flow-edge{" async" if dashed else ""}" d="{coords}" '
        f'fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" '
        f'stroke-linecap="round"{(" stroke-dasharray=\"7 6\"") if dashed else ""}'
        f'{(" marker-end=\"url(#arrow)\"") if arrow else ""}/>' )
    if label:
        # Labels have a dark keyline so the grid and connecting lines never cut letters.
        put("labels", f'<text x="{lx}" y="{ly}" font-size="18" fill="{color}" '
            f'text-anchor="middle" stroke="{BG}" stroke-width="7" paint-order="stroke fill">'
            f'{escape(label)}</text>')


def down(x, y1, y2, label="", lx=None, dashed=False):
    edge([(x, y1), (x, y2)], label, lx or x + 130, (y1 + y2) / 2 + 6, dashed)


def port(x, y, code, caption):
    put("nodes", f'<g><circle cx="{x}" cy="{y}" r="20" fill="{BG}" stroke="{GOLD}" stroke-width="2"/>')
    text(x, y + 7, code, 20, GOLD, 700)
    text(x + 32, y + 7, caption, 18, MUTED, 400, "start")
    put("nodes", "</g>")


def build():
    text(65, 66, "智能电商客服平台 · 端到端详细流程", 40, INK, 700, "start")
    text(65, 110, "补充图 05  /  V1 目标设计  /  2026-09-05  /  当前仅完成 M00.1–M00.3 骨架与治理", 22, GOLD, 400, "start")
    text(65, 152, "从统一入口向下展开：条件分支 → 结果收口 → 异步闭环。KF 是知识分支的核心，不替代整个平台。", 22, MUTED, 400, "start")
    text(65, 188, "实线：处理先后与结果流    虚线：异步事件    圆标 R：同一个结果收口    D1–D6：底部资源定位，不是额外业务步骤", 19, CYAN, 400, "start")

    group("entry", 40, 215, 1920, 920, "01  统一入口与可信上下文", "局域网只开放 Nginx；三个前端不直连内部服务或存储")
    box("start", 670, 275, 660, 90, "起点 · 局域网浏览器发起请求", ["客户端 / 客服工作台 / 管理台"], GOLD, emphasis=True)
    box("n1", 640, 410, 720, 90, "N1 · Nginx 统一入口", ["HTTPS、静态页面、API 与流式连接转发"])
    box("n2", 640, 545, 720, 125, "N2 · API Gateway + IAM", ["身份认证 → 租户 / 角色 / 资源授权 → 限流与输入校验", "服务端生成 request_id / trace_id；D1 身份，D4 限流"])
    box("n3-in", 640, 725, 720, 125, "N3 · Conversation / 会话准备", ["幂等写入用户消息；读取正式历史与摘要；校验附件归属", "输出 conversation_id / message_id + 最小授权上下文；D1 / D2"])
    box("n4-in", 640, 905, 720, 165, "N4 · Orchestration / 确定性业务编排", ["① 明确人工 / 风险优先  ② 恢复已有业务工作流", "③ 缺槽位或低置信 → 澄清  ④ 按业务类型路由", "保存 run_id、决策理由、workflow_id 与状态；D1"], GOLD, emphasis=True)
    down(1000, 365, 410)
    down(1000, 500, 545)
    down(1000, 670, 725, "对话请求", 1120)
    down(1000, 850, 905, "问题 + 历史 + 状态引用", 1155)
    box("context-note", 90, 550, 430, 265, "全程携带的可信标识", ["tenant_id / actor_id：由服务端确认", "request_id / trace_id：串联一次请求", "conversation_id：正式会话", "message_id / run_id：消息与执行", "变更另带幂等键与预期版本", "原始敏感信息不进入公共日志"], MUTED, 19)
    box("page-shortcuts", 1470, 725, 440, 250, "页面操作 · 不经过对话编排", ["P5  商品 / 订单 / 售后 → N5", "P6  知识上传与发布 → N6 / B0", "P7  工单处理与公开回复 → N7", "权限管理 → N2 内的 IAM", "操作结果经 N2 → N1 原路返回", "不伪造聊天记录；细节见图 04"], PURPLE, 19)
    edge([(1360, 607), (1690, 607), (1690, 725)], "非对话页面 API", 1675, 588)
    box("clarify", 90, 930, 430, 115, "澄清 / 等待确认", ["收集订单号、原因等缺失信息", "不执行交易动作；生成下一步问题"], GREEN)
    edge([(640, 987), (520, 987)], "信息不足", 580, 970)
    down(305, 1045, 1080)
    port(305, 1100, "R", "转到统一结果收口")

    group("execution", 40, 1190, 1920, 1490, "02  业务执行分支", "非 Agent 自主调用")
    group("kf", 550, 1245, 910, 1390, "N6 · 知识服务 / KF", "核心顺序与旁路保留")
    edge([(1000, 1070), (1000, 1155), (290, 1155), (290, 1300)])
    edge([(1000, 1155), (855, 1155), (855, 1290)])
    edge([(1000, 1155), (1710, 1155), (1710, 1300)])

    box("n5", 80, 1300, 420, 120, "N5 · Commerce / 电商业务", ["商品、SKU、价格与库存查询", "订单、物流、支付摘要、发票、售后"], CYAN, 19)
    box("n5-guard", 80, 1480, 420, 130, "领域校验与业务状态检查", ["订单 / 资源归属 + 状态合法性", "变更必须确认、幂等、版本校验", "失败返回明确业务原因，不写假成功"], CYAN, 19)
    box("n5-execute", 80, 1670, 420, 160, "查询 / 受控命令执行", ["读取事实，或事务保存获准申请", "D1：本领域事实 + 审计 + Outbox", "ERP / 物流等通过适配器接入", "真实渠道与演示数据分开验收"], CYAN, 19)
    box("n5-result", 80, 1890, 420, 120, "返回结构化业务结果", ["事实字段 + 状态 + 可执行下一步", "N4 可组织措辞，不能改写交易事实"], GREEN, 19)
    down(290, 1420, 1480)
    down(290, 1610, 1670)
    down(290, 1830, 1890)
    box("commerce-boundary", 80, 2190, 420, 275, "业务与知识的边界", ["政策解释：N6 检索知识依据", "具体订单：N5 查询真实业务状态", "退款 / 改址 / 开票：受控领域流程", "模型不自动执行支付或退款", "跨领域只用 API 或版本化事件", "不得直接修改其他模块的数据表"], MUTED, 19)

    box("n6-entry", 590, 1290, 530, 105, "授权包装层 → KF API → QAService", ["校验数据域 / 可见性 / 场景；绑定已发布版本", "调用原有 stream_query；不重排 KF Pipeline"], CYAN, 19)
    box("k0", 590, 1430, 530, 90, "K0 · 创建查询上下文", ["场景、权限范围、会话、Trace、固定 kb_version"])
    box("k1", 590, 1570, 530, 90, "K1 · 低成本路由", ["确定性直答 / FAQ 精确命中 / 继续检索"])
    box("k2", 590, 1710, 530, 95, "K2 · 检索准备", ["历史与意图、按需改写、查询变体", "检索计划、来源过滤与 Prompt Profile"], CYAN, 19)
    box("k3", 590, 1850, 530, 95, "K3 · FAQ 检索与直出判断", ["按计划混合召回 / 可选重排；D3 / D5", "满足直出条件返回标准答案，否则继续"], CYAN, 19)
    box("k4", 590, 1990, 530, 95, "K4 · 文档检索", ["按计划召回与重排；D3 / D5", "输出候选片段、分数和来源元数据"], GOLD, 19)
    box("k5", 590, 2130, 530, 95, "K5 · 答案上下文构建", ["合并 FAQ / 文档证据、裁剪上下文预算", "生成授权范围内的 Prompt 与引用来源"], CYAN, 19)
    box("k6", 590, 2270, 530, 130, "K6 · LLM 流式生成与后处理", ["LangChain 调用 D6：仅发送必要的授权上下文", "引用补充 + 生成后置信检查；不等于事实保证", "token 经 N4 → N3 → N2 → N1 实时展示"], PURPLE, 19)
    box("k7", 590, 2450, 530, 110, "K7 · KF 内部统一收尾", ["D1：KF 历史；Trace；内部 end / error", "返回 answer / sources / 诊断；正式会话另由 N3 保存"], GREEN, 19)
    for start, end in [(1395, 1430), (1520, 1570), (1660, 1710), (1805, 1850), (1945, 1990), (2085, 2130), (2225, 2270), (2400, 2450)]:
        down(855, start, end)
    box("direct", 1160, 1550, 250, 130, "确定性直答", ["边界回复 / FAQ 精确命中", "跳过检索与 LLM", "转同一 K7 收尾"], GREEN, 17)
    box("faq-direct", 1160, 1830, 250, 130, "FAQ 标准答案直出", ["达到直出条件", "跳过文档检索与 LLM", "转同一 K7 收尾"], GREEN, 17)
    box("insufficient", 1160, 2110, 250, 130, "证据不足", ["明确无法确认", "不调用 LLM 编造答案", "转同一 K7 收尾"], GOLD, 17)
    for y, condition in ((1615, "直答"), (1895, "直出"), (2175, "为空")):
        edge([(1120, y), (1160, y)], condition, 1140, y - 17)
        edge([(1410, y), (1440, y), (1440, 2505)], arrow=False)
    text(980, 1691, "继续检索", 18, MUTED)
    text(980, 1974, "未直出", 18, MUTED)
    text(980, 2254, "有可用证据", 18, MUTED)
    edge([(1440, 2505), (1120, 2505)])
    text(1290, 2398, "旁路并入同一收尾", 18, MUTED)
    text(1285, 2565, "异常由包装层 / finish_error 上报", 16, MUTED)
    text(1285, 2595, "内部 end ≠ 平台正式会话成功", 16, MUTED)

    box("n7", 1510, 1300, 400, 130, "N7 · Ticket / 人工工单", ["创建 / 关联工单；权限与重复提交检查", "D1：优先级、状态、摘要、公开性", "工单事实与审计由 N7 持有"], GOLD, 18)
    box("ticket-ack", 1510, 1490, 400, 130, "本轮立即返回工单受理结果", ["ticket_id + 当前状态 + 等待说明", "不等待人工处理完成再结束本轮", "→ R 统一保存受理回复"], GREEN, 18)
    down(1710, 1430, 1490)
    group("human-async", 1490, 1790, 440, 780, "后续人工处理 · 独立事件", "")
    box("human-pick", 1520, 1860, 380, 120, "客服工作台 → N2 → N7", ["排队 / 分派 / 接单 / 处理 / 关闭", "再次验证工单权限与当前状态"], GOLD, 18)
    box("human-write", 1520, 2040, 380, 130, "N7 保存回复与纠错", ["公开回复 + Outbox 同事务", "私密备注仅内部可见", "纠错追加保存，不覆盖原始记录"], GOLD, 18)
    box("human-event", 1520, 2230, 380, 155, "进入 B2 异步任务处理", ["N8 去重消费公开回复事件", "调用 N3 保存正式消息并推送客户", "失败重试 / 死信 / 人工修复", "不能直接把内部备注发给客户"], GREEN, 18)
    down(1710, 1980, 2040, dashed=True)
    down(1710, 2170, 2230, dashed=True)
    text(1710, 2470, "此处是后续事件流程，", 19, MUTED)
    text(1710, 2503, "不是本轮受理回复的等待节点。", 19, MUTED)

    edge([(290, 2010), (290, 2070), (520, 2070), (520, 2730), (1000, 2730), (1000, 2835)])
    edge([(855, 2560), (855, 2730)], arrow=False)
    edge([(1910, 1555), (1940, 1555), (1940, 2730), (1000, 2730)], arrow=False)
    group("response", 40, 2770, 1920, 515, "03  统一结果收口与正式回复", "本轮答案按结果流向下收口；澄清路径也进入 R")
    box("result-r", 610, 2835, 780, 115, "R · N4 校验与封装执行结果", ["answer / sources / route / business_id 或 ticket_id", "脱敏、来源授权、保存运行结果与编排状态；D1"], GOLD, 20, True)
    box("n3-save", 610, 2995, 780, 110, "N3 保存正式会话结果", ["D1：assistant 消息、来源引用、状态与关联 ID；幂等一次写入", "各模块只写自有事实；跨服务事件按幂等与对账保证最终一致"])
    box("client-end", 610, 3150, 780, 95, "正式保存成功 → N2 → N1 → 浏览器最终完成", ["可先展示 token；正式 end 受落库结果约束；支持按消息 ID 查询最终状态"], GREEN, 19)
    down(1000, 2950, 2995)
    down(1000, 3105, 3150)
    box("stream-rule", 100, 2910, 420, 240, "流式与失败处理", ["token 是预览，不代表业务完成", "客户端断连不能重复触发交易", "下游超时 / 存储失败 → 明确 error", "可用时保留失败或部分结果", "不以重试掩盖不确定的写入状态"], MUTED, 19)
    box("result-contract", 1480, 2910, 420, 240, "需要核对的返回数据", ["request_id / trace_id / run_id", "conversation_id / message_id", "answer + 可见 sources + route", "业务 ID / 工单 ID / 状态", "kb_version + 诊断与失败原因"], MUTED, 19)

    group("closure", 40, 3320, 1920, 1250, "04  数据闭环与异步任务", "用户不反馈也保留本轮结果；反馈、入库与人工消息分别触发任务")
    box("feedback", 660, 3390, 680, 125, "B1 · 反馈 / 人工纠错 / 运行失败事件", ["N3 保存用户评价；N7 保存客服纠错；各领域记录运行结果", "原始记录 + Outbox 在本领域同事务保存；D1"], GREEN, 19)
    down(1000, 3245, 3390, "可选评价 + 持续采集运行结果", 1210, True)
    box("upload", 90, 3390, 450, 130, "B0 · 管理台 → N2 → N6", ["授权上传、类型 / 大小 / 哈希校验", "D2 原文；D1 元数据 / 状态 / Outbox", "跨存储用中间状态、补偿与清理"], PURPLE, 18)
    box("worker", 660, 3580, 680, 145, "B2 · Outbox Relay → Redis Streams → N8 Worker", ["事件确认投递；event_id 去重；重试、超时、死信与恢复", "按任务路由；通过所属服务 / 处理器保存结果，不直接越权写表", "D4 承载队列与临时状态，不替代 D1 业务事实"], CYAN, 19)
    down(1000, 3515, 3580, dashed=True)
    edge([(315, 3520), (315, 3550), (1000, 3550)], dashed=True, arrow=False)
    box("index", 90, 3810, 520, 175, "B3a · 知识构建任务 / N6", ["D2 读取原文 → 解析 / 清洗 / 切片", "D5 Embedding → D3 候选索引", "D1 保存块映射、任务状态、版本元数据", "候选版本未验收前不用于线上问答"], PURPLE, 19)
    box("badcase", 710, 3810, 540, 175, "B3b · Bad Case 筛选与审核", ["关联原始消息、版本、Trace 与纠错建议", "归因：知识 / Prompt / 路由 / 业务 / 人工", "知识或配置变更 → 门禁；业务纠错 → N5 / N7", "建议由 N6 外层治理持有，待 M13 契约确定"], GOLD, 18)
    box("reply-worker", 1490, 3810, 420, 175, "B3c · 人工公开回复投递", ["N8 验证事件归属与公开性", "调用 N3 幂等保存正式人工消息", "通知经 N2 / N1 到达授权客户端", "私密备注永不进入客户消息流"], GREEN, 19)
    for cx in (350, 980, 1700):
        edge([(1000, 3725), (1000, 3765), (cx, 3765), (cx, 3810)], dashed=True)
    box("human-delivered", 1490, 4050, 420, 125, "客户接收 / 重连后补查", ["依据 message_id 去重与确认状态", "新评价仍进入 B1，形成后续轮次"], GREEN, 19)
    down(1700, 3985, 4050, dashed=True)
    box("quality", 370, 4090, 760, 120, "B4 · 回归评测与人工审核门禁", ["权限隔离、Golden Set、质量、延迟、失败恢复与业务回归", "关联数据 / 配置 / 索引版本；失败停留候选态，不发布"], GOLD, 20)
    edge([(350, 3985), (350, 4035), (750, 4035), (750, 4090)], dashed=True)
    edge([(980, 3985), (980, 4035), (750, 4035)], dashed=True, arrow=False)
    box("release", 370, 4270, 760, 120, "B5 · 审批后激活知识 / Prompt / 路由版本", ["知识索引完整后再切换；按版本绑定缓存；保存发布审计", "发布异常回退到上一可用版本；权限撤销先于异步清理"], GOLD, 20)
    box("cycle", 370, 4450, 760, 90, "B6 · 新请求读取已发布版本 → 返回 N4 / N6", ["线上效果继续进入 B1；V1 闭环到此完成"], GREEN, 20)
    down(750, 4210, 4270, dashed=True)
    down(750, 4390, 4450, dashed=True)
    box("failure-note", 1240, 4250, 670, 275, "健壮性检查 · 各层分别负责", ["入口：拒绝越权、超限、非法输入；不进入业务执行", "业务：校验归属与状态；提交不明先查幂等结果再重试", "检索：先授权后召回；证据不足明确说明；依赖失败降级", "异步：可重入、可追踪、可重放；死信有人工修复入口", "数据：备份恢复、版本回滚、删除补偿与对账须验收", "全链路：脱敏、最小上下文、操作审计，不依赖模型自觉"], MUTED, 19)

    group("resources", 40, 4630, 1920, 570, "05  底部资源与所有权", "资源定位符 D1–D6 在对应处理节点中标注；下方箭头是读写 / 调用关系，不是业务主干")
    resources = [
        ("d1", 80, "N2 / N3 / N4 / N5 / N6 / N7", "读写各自逻辑数据域", "D1 · MySQL", ["身份、会话、业务、工单", "知识元数据、版本、Outbox"], GOLD),
        ("d2", 395, "N3 附件 / N6 知识处理器", "授权读写原文与附件", "D2 · MinIO", ["原文与附件对象", "权限引用保存在所属领域"], CYAN),
        ("d3", 710, "N6 检索 / 知识构建处理器", "查已发布 / 写候选索引", "D3 · Milvus", ["混合检索所需派生索引", "可从原文与元数据重建"], GREEN),
        ("d4", 1025, "入口 / Outbox Relay / N8", "限流、缓存、发布与消费", "D4 · Redis / Streams", ["缓存、临时状态、任务队列", "不保存唯一业务事实"], CYAN),
        ("d5", 1340, "N6 检索 / 知识构建处理器", "query / chunks / 候选文本", "D5 · 向量与重排", ["Embedding / Reranker", "文本向量、候选重排序", "模型与索引版本兼容"], PURPLE),
        ("d6", 1655, "N6 生成 / 授权摘要任务", "最小上下文 → 文本 / token", "D6 · LLM", ["基于证据生成、必要摘要", "不持有交易执行权限"], PURPLE),
    ]
    for key, x, consumer, relationship, title, lines, color in resources:
        cx = x + 132
        text(cx, 4730, consumer, 17, MUTED)
        edge([(cx, 4745), (cx, 4820)], relationship, cx, 4788, False, color)
        # Cylinders denote persistence; model boxes are deliberately not databases.
        if key in {"d1", "d2", "d3", "d4"}:
            put("nodes", f'<g id="{key}"><path d="M{x},4840 A132,20 0 0 1 {x+264},4840 '
                f'L{x+264},4950 A132,20 0 0 1 {x},4950 Z" fill="{PANEL}" stroke="{color}" stroke-width="2"/>'
                f'<ellipse cx="{cx}" cy="4840" rx="132" ry="20" fill="{PANEL}" stroke="{color}" stroke-width="2"/>')
            text(cx, 4886, title, 22, color, 700)
            for i, line in enumerate(lines):
                text(cx, 4915 + i * 26, line, 18)
            put("nodes", "</g>")
        else:
            box(key, x, 4820, 264, 140, title, lines, color, 18)
    box("n9", 90, 5015, 1820, 140, "N9 · 全链路可观测性与领域审计（横切能力，不是额外业务关卡）", ["所有节点按 trace_id 关联脱敏日志、耗时、错误与指标；运行日志不代替领域事务审计。V1 用 Compose 部署，逻辑模块可按负载合并运行。", "版本路线：V1 平台与闭环 → V1.5 KF 质量 / 性能优化 → V2 受控 Agent → V3 知识图谱；本图没有把后续能力画成已建成功能。"], MUTED, 20)
    text(65, 5240, "依据：模块边界 / ADR-0001 / V1 审查资料 / KF 只读源码。此图为规划审查补充，不变更任何参考项目或 KF 核心架构。", 18, MUTED, 400, "start")

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="diagram-title diagram-description">
<title id="diagram-title">智能电商客服平台 V1 端到端详细流程</title>
<desc id="diagram-description">从局域网统一入口，经鉴权、会话与编排，进入商务、KF 或人工分支，汇合为正式回复，再展开知识与反馈闭环及资源所有权。当前只实现 M00.1 至 M00.3。</desc>
<defs><pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40,0H0V40" fill="none" stroke="#213449" stroke-width="1"/></pattern>
<marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L8,4 L0,8 Z" fill="{CYAN}"/></marker>
<filter id="glow" x="-10%" y="-25%" width="120%" height="150%"><feDropShadow dx="0" dy="0" stdDeviation="6" flood-color="{GOLD}" flood-opacity=".2"/></filter></defs>
<style>text{{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif}} .node:hover rect{{stroke-width:3}}</style>
<rect width="{WIDTH}" height="{HEIGHT}" fill="{BG}"/><rect width="{WIDTH}" height="{HEIGHT}" fill="url(#grid)"/>
{''.join(''.join(layers[key]) for key in layers)}
</svg>'''
    (OUT / f"{STEM}.svg").write_text(svg, encoding="utf-8")
    template = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V1 平台端到端详细流程 · 补充图 05</title><style>
*{box-sizing:border-box}body{margin:0;background:#0c1524;color:#eef6ff;font:15px/1.6 "Microsoft YaHei",sans-serif}header{position:sticky;top:0;z-index:5;padding:16px 24px;background:#101e30f7;border-bottom:1px solid #30475d;backdrop-filter:blur(10px)}h1{font-size:23px;margin:0 0 4px}p{margin:4px 0;color:#a7bbd0}nav,.tools{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}button,a{font:inherit;color:#91daec;background:#16283b;border:1px solid #35516a;border-radius:6px;padding:5px 12px;text-decoration:none;cursor:pointer}button:hover,a:hover{border-color:#f0ba54;color:#f0ba54}output{padding:5px 10px;color:#f0ba54}main{padding:24px;overflow:visible}#chart svg{display:block;max-width:none;height:auto}small{font-size:13px}a.return{border-color:#65568f;color:#ccb8ff}@media print{header{position:static}nav,.tools{display:none}main{padding:0}#chart svg{width:100%!important}}
</style></head><body><header><h1>项目端到端详细流程 · 补充图 05</h1>
<p>参考示例的阅读方式，按本项目重新组织模块与数据流；不是复制示例的 RAG 架构。当前图中业务能力为 V1 目标设计。</p>
<nav aria-label="流程区域"><button data-jump="entry">01 统一入口</button><button data-jump="execution">02 业务分流</button><button data-jump="kf">展开 KF 核心</button><button data-jump="response">03 回复收口</button><button data-jump="closure">04 数据闭环</button><button data-jump="resources">05 底部资源</button></nav>
<div class="tools"><button id="fit">适应宽度</button><button id="minus" aria-label="缩小">−</button><output id="zoom" aria-live="polite"></output><button id="plus" aria-label="放大">＋</button><button id="actual">原始尺寸</button>
<a download href="__STEM__.png">高清 PNG</a><a download href="__STEM__.svg">可编辑 SVG</a><a class="return" href="V1项目架构图.html">原四张审查图</a></div>
<p><small>实线＝处理顺序；虚线＝异步；R＝同一结果收口；D1–D6＝资源定位。页面操作跳过对话编排；人工后续回复不阻塞本轮受理结果。</small></p>
</header><main><div id="chart">__SVG__</div></main><script>
const svg=document.querySelector('#chart svg'), output=document.querySelector('#zoom');let scale=1;
function setScale(value){scale=Math.max(.25,Math.min(2,value));svg.style.width=(2000*scale)+'px';output.value=Math.round(scale*100)+'%';}
function fit(){setScale((window.innerWidth-48)/2000);}
document.querySelector('#fit').onclick=fit;document.querySelector('#actual').onclick=()=>setScale(1);
document.querySelector('#minus').onclick=()=>setScale(scale-.15);document.querySelector('#plus').onclick=()=>setScale(scale+.15);
document.querySelectorAll('[data-jump]').forEach(button=>button.onclick=()=>{const target=document.getElementById(button.dataset.jump);const top=target.getBoundingClientRect().top+window.scrollY-document.querySelector('header').getBoundingClientRect().height-12;window.scrollTo({top,left:0,behavior:'instant'});});
fit();
</script></body></html>'''
    (OUT / "V1平台端到端详细流程.html").write_text(template.replace("__STEM__", STEM).replace("__SVG__", svg), encoding="utf-8")
    print(f"Generated {STEM}.svg and offline HTML ({WIDTH} x {HEIGHT}).")


if __name__ == "__main__":
    build()
