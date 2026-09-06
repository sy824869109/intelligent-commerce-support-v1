"""One connected V1 technical map with guided viewport steps.

Code-native SVG/HTML documentation only. Does not import either reference project,
start services, modify KF stages, or claim business acceptance has been executed.
Short node labels show topology; click details explain ownership and synthetic data.
"""
from html import escape
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]
W, H = 3200, 6600
STEM = "14_V1全景技术流程图"
TITLE = "V1全景技术流程图_逐步讲解.html"
COLORS = dict(cyan="#62cee6", gold="#f5bd62", green="#78d7af", purple="#c0aaff", red="#ef929e", gray="#97b0cd")
nodes, edges, groups, phases = [], [], [], []


def node(key, x, y, w, title, lines, *, h=110, color="cyan", shape="rect", detail="", example=""):
    nodes.append(dict(id=key,x=x,y=y,w=w,h=h,title=title,lines=lines,color=color,shape=shape,detail=detail,example=example))


def edge(a,b,points,label="",at=None,*,kind="flow",color="cyan"):
    edges.append(dict(a=a,b=b,points=points,label=label,at=at,kind=kind,color=color))


def down(a,b,x,y1,y2,label="",*,kind="flow",color="cyan"):
    edge(a,b,[(x,y1),(x,y2)],label,(x+155,(y1+y2)/2),kind=kind,color=color)


def group(x,y,w,h,title,subtitle="",color="cyan"):
    groups.append(dict(x=x,y=y,w=w,h=h,title=title,subtitle=subtitle,color=color))


def phase(title, ids, bounds, explanation, example):
    phases.append(dict(title=title,ids=ids.split(),bounds=bounds,explanation=explanation,example=example))


def build_data():
    group(1010,130,1080,980,"01  统一入口 → 正式会话 → 业务路由","客户聊天从这里往下走；页面操作在鉴权后分流")
    node("user",1280,210,610,"局域网用户 / 客服 / 管理员",["打开三端页面，发起聊天或页面操作"],h=85,color="gold",example="顾客：O1001 的杯子裂了，可以申请退货吗？")
    node("nginx",1280,345,610,"N1 · Nginx 统一入口",["HTTPS / 静态页面 / API / 流式连接"],h=85,detail="局域网只对客户端开放受控入口；浏览器不直接连接内部数据库和模型。")
    node("auth",1230,485,710,"N2 · Gateway / IAM",["认证 → 租户与角色 → 输入校验 / 限流","传递 actor / tenant / request_id / trace_id"],detail="后续领域服务仍需校验资源归属与业务权限。未认证、越权、超限请求在相应入口明确拒绝。")
    node("session",1230,665,710,"N3 · 保存输入，读取会话控制",["正式用户消息 + 活动 Run 预留 / epoch","授权历史快照；当前问题单独传入"],detail="HUMAN 模式的客户消息通知人工，不启动可公开回复的 AI Run。AI 资格由 N3 预留，N4 持有 Run。")
    node("router",1230,910,710,"N4 · 按优先级决定路径",["安全 / 人工 → 已有 Workflow → 信息补齐","只读 / 知识 / 混合咨询 / 受控申请"],h=125,color="gold",shape="decision",detail="确定性编排不是 Agent 自主调用。已有工作流优先处理取消、修改、继续或确认，不能每轮重新分类后丢失状态。")
    down("user","nginx",1585,295,345)
    down("nginx","auth",1585,430,485)
    down("auth","session",1585,595,665,"聊天请求")
    down("session","router",1585,775,910,"允许 AI 的本轮输入")

    group(130,180,780,870,"例外先处理，不进入业务执行","失败 / 澄清是明确出口，不是假成功",color="gold")
    node("reject",210,380,620,"入口拒绝 / 安全错误",["未登录、越权、超限、非法输入","返回安全错误；不泄露他人资源"],color="red")
    node("ticketfailure",210,550,620,"建单失败：尚未成功受理",["查同 handoff ID / 有界重试；返回真实失败说明"],h=90,color="red")
    edge("auth","reject",[(1230,540),(1000,540),(1000,435),(830,435)],"认证或入口检查失败",(1030,405),color="red")
    node("clarify",210,695,620,"N4 · 澄清 / 拒绝不支持的动作",["缺订单 / 商品行 → 让用户选择","不确定不编造；不执行交易"],color="gold",example="“帮我退那个”但有两笔订单：先询问是哪一笔。")
    node("clarifyresult",270,875,500,"形成澄清或边界说明",["进入下方统一结果收口 R"],h=85,color="green")
    edge("router","clarify",[(1230,970),(990,970),(990,750),(830,750)],"需补充信息 / 明确拒绝",(1000,725),color="gold")
    down("clarify","clarifyresult",520,805,875)
    edge("clarifyresult","result",[(270,918),(65,918),(65,4180),(1060,4180),(1060,4255),(1230,4255)],"澄清也正式保存",(285,4058),color="green")

    group(2270,180,790,870,"页面分流 · 不伪造聊天","三端页面经过 N2，再调用对应领域",color="purple")
    node("page",2340,365,650,"页面操作按领域分发",["订单 / 售后页 → N5；知识页 → N6","客服台 → N7；权限管理 → N2"],color="purple",detail="只读页面不经过 N4 意图识别；页面申请使用同一 N5 预检与提交端口，channel=PAGE 不是权限例外。")
    node("pageread",2340,580,650,"N2 → N5 · 业务页面查询",["校验归属 → 读订单 / 包裹 / 售后事实","查询结果经 N2 / N1 返回页面"],color="purple")
    node("pagewrite",2340,790,650,"页面申请：预检 → 明确确认",["同一 N5 submit / query，详情见下方申请链","不需要 conversation_id / N4 Workflow"],color="purple",detail="页面生成 N5 preflight，明确确认后调用统一提交端口。下方共享的是领域预检、确认约束和命令端口；N4 的会话草稿 / 确认记录仅用于聊天。")
    edge("auth","page",[(1940,540),(2170,540),(2170,420),(2340,420)],"非聊天页面 API",(2120,395),color="purple")
    down("page","pageread",2665,475,580,"只读")
    edge("page","pagewrite",[(2990,420),(3030,420),(3030,845),(2990,845)],"申请",(3030,745),color="purple")

    group(130,1170,800,1810,"02A  电商事实与混合资格判断","订单事实归 N5；N4 按顺序协调 N5 → N6 → N5")
    node("businessauth",210,1280,640,"N5 · 业务资源守卫",["订单归属 / 商品行 / 数量 / 当前状态","商品、订单、包裹、支付摘要、发票、售后"],detail="例中使用演示订单；LIVE/DEMO/HUMAN_ONLY/UNSUPPORTED 必须对用户明示。该图不表示所有渠道已接入。")
    node("facts",210,1490,640,"N4 调 N5 · 读取真实事实",["返回结构化结果 + 更新时间 + facts_version","事实缺失不由模型猜测"],example="O1001/L1，签收 2 天，数量 1，尚无占用数量的售后申请。")
    node("needpolicy",210,1710,640,"只查事实，还是需要政策判断？",["只读 → 直接收口；混合咨询 → 请求 N6","由 N4 协调，不是 N5 直接调用 KF"],h=125,color="gold",shape="decision")
    node("readresult",210,1980,640,"只读结果：物流 / 订单 / 商品等",["返回实际状态及时间；进入 R","多个包裹逐个列出，不合成一个假状态"],color="green",example="顾客只问物流：答包裹当前位置，不调用退款申请。")
    node("policycall",210,2200,640,"N4 · 构造最小政策查询",["商品属性 / 区域 / 适用时间依据 / 知识范围","N6 只返回政策证据，不判订单审批"],color="gold")
    node("rules",210,2500,640,"证据返回 N4 → 调 N5 批准规则",["核对事实、适用政策、数量与版本","输出 ELIGIBLE / INELIGIBLE / REVIEW / UNKNOWN"],color="gold",detail="完整资格枚举使用标准的 ELIGIBLE / INELIGIBLE / REVIEW_REQUIRED / UNKNOWN；节点中的 REVIEW 为显示缩写。规则缺失或冲突不能由 LLM 自行补规则。")
    node("eligibility",210,2720,640,"N4 · 组合事实、依据和下一步",["可申请 ≠ 审批通过 ≠ 退款到账","只咨询就在 R 结束；主动办理需后续确认"],color="green",example="虚构 P003/RULE003：签收 14 天内可提交破损申请，仍待审核；不是法律或真实商家承诺。")
    edge("router","businessauth",[(1230,990),(1060,990),(1060,1135),(530,1135),(530,1280)],"业务只读 / 混合咨询",(690,1112))
    down("businessauth","facts",530,1390,1490)
    down("facts","needpolicy",530,1600,1710)
    down("needpolicy","readresult",530,1835,1980,"只读")
    edge("needpolicy","policycall",[(850,1770),(900,1770),(900,2255),(850,2255)],"混合",(900,2115),color="gold")
    edge("readresult","result",[(210,2035),(90,2035),(90,4168),(1080,4168),(1080,4255),(1230,4255)],color="green")
    down("rules","eligibility",530,2610,2720)
    edge("eligibility","result",[(210,2775),(115,2775),(115,4158),(1100,4158),(1100,4255),(1230,4255)],"咨询到此结束，不自动建单",(550,4135),color="green")

    group(980,1170,1240,1810,"02B  N6 · KF 原有 RAG Pipeline","平台外层接权限 / 正式历史；保留 K0–K7 顺序及已有旁路")
    node("kfwrap",1050,1250,780,"N6 授权包装 → 原 KF 入口",["请求级 History Adapter：只读 N3 正式授权快照","隔离诊断历史；固定已发布、兼容的 kb_version"],detail="禁止临时替换共享单例 history。当前问题单独传递；私密备注、未发布草稿不回灌。适配实现由后续 M09 合同与 ADR 冻结。")
    node("k0",1050,1410,450,"Stage 0 · 查询上下文",["create_query_context","场景 / 权限 / 会话 / Trace"],h=105)
    node("k1",1050,1570,450,"Stage 1 · 低成本路由",["decide_route","确定性直答 / FAQ 精确 / 检索"],h=105,color="gold")
    node("direct",1030,1760,310,"确定性 / FAQ 精确直答",["无需检索和 LLM → K7"],h=85,color="green")
    node("k2",1460,1760,650,"Stage 2 · 检索准备",["历史 / 意图 / 按需改写 / 查询变体","检索计划、来源过滤、Prompt Profile"],h=105)
    node("k3",1270,1950,520,"Stage 3 · FAQ 检索",["按计划混合召回 / 可选重排","满足直出条件？"],h=105)
    node("faq",1040,2150,280,"FAQ 标准答案直出",["跳过文档与 LLM → K7"],h=85,color="green")
    node("k4",1560,2150,560,"Stage 4 · 文档检索 + 重排",["按原计划执行可用检索分支","候选片段 / 分数 / 来源元数据"],h=105,color="gold")
    node("k5",1560,2330,560,"Stage 5 · 组织答案上下文",["合并证据 / 裁剪预算 / 绑定引用","证据是否足够？"],h=105,color="gold")
    node("empty",1100,2470,350,"证据不足，明确无法确认",["不编造答案 → K7"],h=85,color="red")
    node("k6",1760,2530,405,"Stage 6 · LLM 生成",["LangChain / 模型 → 候选答案","引用等后处理；高风险缓冲"],h=105)
    node("k7",1760,2760,405,"Stage 7 · KF 统一收尾",["隔离诊断历史 / Trace / end","子调用完成 ≠ 平台正式完成"],h=105,color="green")
    edge("router","kfwrap",[(1585,1035),(1585,1130),(1440,1130),(1440,1250)],"纯知识咨询",(1680,1120))
    edge("policycall","kfwrap",[(850,2255),(955,2255),(955,1305),(1050,1305)],"N4 调 N6：最小业务属性",(1010,2310),color="gold")
    edge("kfwrap","k0",[(1275,1360),(1275,1410)])
    down("k0","k1",1275,1515,1570)
    edge("k1","direct",[(1050,1625),(1015,1625),(1015,1802),(1030,1802)],"直答",(1017,1715))
    edge("k1","k2",[(1500,1625),(1785,1700),(1785,1760)],"retrieval",(1700,1680))
    edge("k2","k3",[(1785,1865),(1530,1910),(1530,1950)])
    edge("k3","faq",[(1270,2002),(1180,2090),(1180,2150)],"可直出",(1145,2075))
    edge("k3","k4",[(1790,2002),(1840,2080),(1840,2150)],"未直出",(1950,2095))
    down("k4","k5",1840,2255,2330)
    edge("k5","empty",[(1560,2380),(1275,2430),(1275,2470)],"不足",(1380,2420),color="red")
    edge("k5","k6",[(1840,2435),(1962,2480),(1962,2530)],"有证据",(2050,2460))
    down("k6","k7",1962,2635,2760,"候选答案")
    edge("direct","k7",[(1030,1802),(1000,1802),(1000,2930),(1962,2930),(1962,2865)],"直答旁路 → 同一 K7",(1400,2920),color="green")
    edge("faq","k7",[(1040,2192),(1010,2192),(1010,2910),(1962,2910),(1962,2865)],color="green")
    edge("empty","k7",[(1275,2555),(1275,2890),(1962,2890),(1962,2865)],color="red")
    edge("k7","rules",[(1760,2812),(1650,2812),(1650,2960),(945,2960),(945,2555),(850,2555)],"混合：证据返回 N4，再由 N4 调 N5",(1350,2977),color="gold")
    edge("k7","result",[(2165,2812),(2240,2812),(2240,3020),(3115,3020),(3115,4225),(2060,4225),(2060,4255),(1940,4255)],"纯知识 / 兜底结果 → R",(2740,3000),color="green")

    group(2290,1170,770,2010,"02C  人工：本轮受理与后续回复分开","先受理回执，再由独立事件完成接管及回复",color="gold")
    node("pending",2350,1280,640,"N4 → N3 · 先进入待人工",["HANDOFF_PENDING / 新控制 epoch","隔离旧 AI 输出；废止未使用的确认"],color="gold")
    node("ticket",2350,1450,640,"N7 · 幂等创建或关联工单",["handoff_request_id → 真实 ticket_id","失败只能显示尚未受理，不能编造排队"],color="gold")
    node("ticketack",2350,1620,640,"本轮只返回真实受理说明",["ticket_id + 当前状态 → R 正式保存","不等待客服接单才结束本轮"],color="green")
    edge("router","pending",[(1940,970),(2190,970),(2190,1135),(2670,1135),(2670,1280)],"明确人工 / 高风险需人工",(2510,1115),color="gold")
    down("pending","ticket",2670,1390,1450)
    down("ticket","ticketack",2670,1560,1620,"拿到真实 ticket_id")
    edge("ticket","ticketfailure",[(2350,1505),(2250,1505),(2250,1100),(975,1100),(975,595),(830,595)],"建单失败",(2250,1475),color="red")
    edge("ticketfailure","result",[(210,595),(50,595),(50,4188),(1040,4188),(1040,4275),(1230,4275)],color="red")
    edge("ticketack","result",[(2990,1675),(3140,1675),(3140,4225),(2060,4225),(2060,4255),(1940,4255)],"本轮受理结果",(2990,4050),color="green")
    node("humaninbox",2350,1780,640,"已有人工控制：收件箱 / 待接单材料",["HUMAN → 当前客服；待人工 → 排队补充材料","客户每条新消息不重新认领或接管"],h=100,color="gold")
    node("assign",2350,1900,640,"后续事件：客服唯一认领",["N7 权限 / 工单版本 / assignment_id","已是 HUMAN 的消息直达客服收件箱"],color="gold",detail="人工模式下不重建工单或启动新 AI 答复。双客服竞争只产生一个有效分配；这一步不是本轮受理请求必须等待的步骤。")
    node("human",2350,2080,640,"N7 → N3 · 版本化接管握手",["N3 CAS 确认 HUMAN 后才开放回复","回执丢失查同 assignment，不重复分配"],color="gold")
    node("reply",2350,2260,640,"N7 · 保存公开回复与 Outbox",["当前分配 / 权限校验；原稿留存","内部备注不生成面向客户的公开事件"],color="gold")
    node("replyworker",2350,2450,640,"Relay → Redis Streams → N8",["只投递已提交公开事件，按 event_id 去重","Worker 调 N3 处理器，不直接改别人表"])
    node("inbox",2350,2650,640,"N3 · Inbox + 正式消息 + 通知",["三者在本地事务提交后才 ACK","ACK 丢失重投原事件，仍是同一条消息"],color="green")
    node("humandelivered",2350,3070,640,"授权客户收到人工公开回复",["断线可补查；保留原客服署名","关工单 ≠ 交还控制 ≠ 售后办结"],color="green",h=95)
    edge("ticketack","assign",[(2350,1675),(2320,1675),(2320,1955),(2350,1955)],"后续认领",(2300,1880),kind="event",color="gold")
    down("assign","human",2670,2010,2080)
    down("human","reply",2670,2190,2260)
    down("reply","replyworker",2670,2370,2450,kind="event")
    down("replyworker","inbox",2670,2560,2650,kind="event")
    edge("inbox","humandelivered",[(2990,2705),(3020,2705),(3020,3120),(2990,3120)],kind="event",color="green")
    edge("session","humaninbox",[(1940,720),(2150,720),(2150,1090),(3085,1090),(3085,1825),(2990,1825)],"HUMAN / 待人工：新消息通知人工，不开启 AI",(2650,1070),kind="event",color="gold")
    edge("humaninbox","reply",[(2990,1825),(3040,1825),(3040,2315),(2990,2315)],"仅已 HUMAN：按有效分配回复",(3060,2410),kind="event",color="gold")

    group(130,3230,2930,800,"03  受控申请：没有明确确认，就没有提交","聊天有 N4 草稿；页面无 N4 Workflow；两者共用 N5 预检 / 命令守卫",color="gold")
    node("draft",210,3350,590,"聊天：N4 收集 / 恢复草稿",["动作、订单行、数量、原因、READY 附件","主动请求办理才进入；不是咨询自动续办"],color="gold",example="“我要申请退货”可以准备草稿；“我再看看”不能消耗确认。")
    node("preflight",900,3480,580,"N5 · 预检并签发 preflight_id",["当前权限 / 事实 / 规则 / 剩余数量","摘要、payload_hash、版本、有效期"],color="gold",example="演示 PF01：L1×1，申请金额 19900 分 CNY；不是最终退款承诺。")
    node("confirm",1590,3600,610,"用户明确确认同一份摘要",["核对动作 / 数量 / 理由 / 金额与后果","修改或过期 → 新预检 + 新确认"],color="gold",shape="decision",h=125)
    node("submit",2320,3730,650,"N5 · 统一 submit：重新校验并幂等",["聊天 N4 先持久化确认消耗 / 命令意图 / Outbox","页面直达 N5；同预检只映射一个 command_id"],color="gold")
    node("commandresult",2320,3910,650,"查询原命令，返回真实申请结果",["未知先查同 command_id / 对账，不能换键重办","申请 AS001 待审核 ≠ 审批成功 / 退款到账"],color="green",h=105)
    edge("router","draft",[(1230,1015),(1085,1015),(1085,1135),(875,1135),(875,3200),(505,3200),(505,3350)],"已有 Workflow / 主动申请 → 相应步骤",(580,3177),color="gold")
    edge("draft","preflight",[(800,3405),(1190,3440),(1190,3480)],"收齐且可预检",(1030,3420),color="gold")
    edge("preflight","confirm",[(1480,3535),(1895,3570),(1895,3600)],"预检通过 → 展示摘要",(1700,3540),color="gold")
    edge("confirm","submit",[(2200,3662),(2645,3700),(2645,3730)],"明确确认",(2420,3678),color="gold")
    edge("confirm","preflight",[(1895,3725),(1895,3890),(1190,3890),(1190,3590)],"修改 / 过期：返回预检；不提交",(1490,3870),color="red")
    down("submit","commandresult",2645,3840,3910)
    edge("submit","preflight",[(2970,3785),(3005,3785),(3005,4050),(1530,4050),(1530,3450),(1190,3450),(1190,3480)],"已明确拒绝的版本 / 凭据变化：重新预检和确认",(2080,4040),color="red")
    edge("commandresult","result",[(2320,3962),(2250,3962),(2250,4100),(1860,4100),(1860,4200)],"仅 CHAT：真实结果 / 待确认",(2040,4080),color="green")
    node("pageresult",2310,4090,680,"仅 PAGE：N5 结果经 N2 / N1 返回页面",["刷新 / 断线查询原 command_id 与申请事实","不经过 N4 / N3，不伪造聊天记录"],color="purple")
    down("commandresult","pageresult",2645,4015,4090,"仅 PAGE",color="purple")
    edge("pagewrite","preflight",[(2990,845),(3160,845),(3160,3270),(1190,3270),(1190,3480)],"页面申请进入同一 N5 预检；不进入聊天草稿",(2460,3255),color="purple")

    group(1020,4080,1140,690,"04  R · 统一结果收口与正式发布","候选答案、领域事实、浏览器送达是三个不同完成时点",color="green")
    node("result",1230,4200,710,"N4 · 检查结果 / 权限 / 控制资格",["来源授权、脱敏、Run / epoch、关联业务 ID","普通 delta 是草稿；高风险仅进度、缓冲后发布"],color="gold",detail="KF start/status/token/end 映射平台进度、受控草稿和子调用结果。KF end 不直接变 run.completed；error 无真实降级结果则失败。")
    node("save",1230,4380,710,"N3 · 正式消息 + 通知 Outbox",["同事务校验发布资格 / 唯一键 / 正式保存","失败只补同一结果发布，不重跑 KF / 业务"],color="green")
    node("done",1230,4560,710,"正式保存后 → N2 / N1 → 浏览器",["message.committed → run.completed","正式全文替换草稿；重连鉴权 / 补查 / 去重"],color="green")
    down("result","save",1585,4310,4380)
    down("save","done",1585,4490,4560,"正式保存成功")
    node("outputfailure",2310,4260,680,"统一错误 / 发布抑制 / 可恢复状态",["旧 epoch、撤权、依赖故障、结果未知分别处理","保存失败只补同一发布；旧草稿不回灌历史"],color="red",detail="普通输出发送前受控；已发送字节无法撤回。N3 保存失败与客户端未收到是不同故障，必须查询正式保存证据；不重跑 KF 或领域命令。")
    edge("result","outputfailure",[(1940,4255),(2250,4255),(2250,4315),(2310,4315)],"不满足发布条件",(2130,4220),color="red")
    edge("save","outputfailure",[(1940,4435),(2250,4435),(2250,4315),(2310,4315)],"正式保存失败",(2140,4410),color="red")

    group(130,4420,820,780,"05A  用户反馈 / 人工纠错 / 错误事件","不是收到差评就直接改知识库",color="purple")
    node("feedback",210,4510,650,"N3 评价 / N7 纠错 / 各域运行证据",["关联 message / run / Trace / 知识与规则版本","保留原始记录 + 本领域 Outbox"],color="purple")
    node("worker",210,4770,650,"Outbox Relay → Streams → N8",["至少一次投递；超时、重试、死信与可重放","目标领域 Inbox + 效果提交后才 ACK"])
    node("triage",210,4980,650,"审核归因 → 责任领域修复项",["知识 N6 / 路由 N4 / 业务 N5 / 人工 N7","跨领域总工作项归属待 M13 ADR"],color="purple")
    edge("done","feedback",[(1230,4615),(1050,4615),(1050,4565),(860,4565)],"用户可选评价；运行证据持续采集",(1230,4720),kind="event",color="purple")
    down("feedback","worker",535,4620,4770,kind="event")
    down("worker","triage",535,4880,4980,kind="event")

    group(2250,4450,810,650,"05B  管理台知识上传入口","经过 N2 授权，原文就绪不等于线上可检索",color="purple")
    node("upload",2340,4590,650,"N6 · 授权上传 / 内容安全检查",["类型、大小、真实格式、哈希与权限范围","原文入 MinIO；N6 元数据 / 状态入 MySQL"],color="purple")
    node("ready",2340,4800,650,"跨存储校验：VALIDATING → READY",["原文与元数据不一致先隔离 / 补偿","检查失败不可默认安全通过"],color="purple")
    edge("page","upload",[(2990,450),(3180,450),(3180,4515),(2665,4515),(2665,4590)],"知识管理页面",(2890,4490),color="purple")
    down("upload","ready",2665,4700,4800)

    group(130,5150,2930,1010,"06  候选构建 → 独立回归 → 审批激活 → 新请求验证","修复反馈、发布效果与下一轮服务相连；V1.5 / Agent / 知识图谱不混入本版执行链",color="purple")
    node("fix",780,5260,670,"审核修订：本例为知识修复",["基于批准资料修订；不是凭差评杜撰政策","其他领域修复分别走其测试与发布流程"],color="purple")
    node("build",2070,5280,830,"N6 处理器：解析 → 切片 → 向量化",["N8 调度；写 Milvus 候选索引 / MySQL 版本与块映射","source_hash + 配置 + 目标版本去重；不越界写表"],color="purple")
    node("candidate",1710,5470,710,"候选知识版本与兼容性检查",["线上仍使用已发布版本；模型 / 索引必须兼容","候选版本不可直接进入正式问答"],color="purple")
    node("quality",1060,5650,720,"独立回归 / 安全 / 质量 / 性能门禁",["原 Bad Case + 独立 Golden Set + 故障恢复","门禁未冻结或未通过：留候选，不能发布"],color="gold",shape="decision",h=125)
    node("release",590,5870,740,"审批激活兼容版本并保留发布审计",["知识 / 规则 / Router / Prompt 由各所属领域拥有","失败保留或回退已验证版本；撤权优先"],color="purple")
    node("nextrequest",210,6040,650,"新请求读取已发布版本并验证改进",["反馈 → 修复 → 回归 → 发布 → 新服务可追溯","这是下一轮请求，不是复活旧 Run"],color="green")
    edge("triage","fix",[(535,5090),(535,5195),(1115,5195),(1115,5260)],kind="event",color="purple")
    edge("fix","upload",[(1450,5315),(1900,5315),(1900,5120),(2220,5120),(2220,4645),(2340,4645)],"修订原文也要检查 / READY 后才构建",(1770,5295),kind="event",color="purple")
    edge("ready","build",[(2665,4910),(2665,5280)],"READY 原文构建任务",(2810,5170),kind="event",color="purple")
    edge("build","candidate",[(2485,5390),(2065,5430),(2065,5470)],kind="event")
    edge("candidate","quality",[(2065,5580),(1420,5620),(1420,5650)],kind="event")
    edge("quality","release",[(1420,5775),(960,5820),(960,5870)],"回归通过 + 审批",(1230,5810),kind="event",color="purple")
    edge("quality","fix",[(1060,5712),(990,5712),(990,5520),(1115,5520),(1115,5370)],"失败 → 回修复",(1090,5490),kind="event",color="red")
    edge("release","nextrequest",[(960,5980),(535,6010),(535,6040)],kind="event",color="green")
    edge("nextrequest","user",[(210,6095),(35,6095),(35,120),(2055,120),(2055,252),(1890,252)],"下一轮服务：新请求 + 已发布版本",(380,160),kind="event",color="purple")

    group(130,6220,2930,325,"底部资源 · 虚线仅表示依赖 / 逻辑归属，不是额外业务步骤","各领域只写自己的数据；向量库可重建，Redis 不能保存唯一业务事实",color="gray")
    resources=[("mysql",175,460,"D1 · MySQL",["身份 / 会话 / Run / 业务 / 工单","知识元数据 / 版本 / Outbox / Inbox"],"green"),
               ("minio",685,360,"D2 · MinIO",["知识原文 / 客户附件","按授权引用，非裸路径通行"],"cyan"),
               ("milvus",1095,390,"D3 · Milvus",["已发布查询 / 候选构建","文档与 FAQ 派生检索索引"],"green"),
               ("redis",1535,390,"D4 · Redis / Streams",["限流 / 缓存 / 临时投递","故障从事实与 Outbox 恢复"],"cyan"),
               ("embed",1975,450,"D5 · Embedding / Reranker",["查询 / 块向量与候选重排","按选型基线，不复制示例模型版本"],"gold"),
               ("llm",2475,510,"D6 · LLM / LangChain 调用",["基于授权证据生成 / 必要摘要","没有交易执行权限"],"purple")]
    for key,x,w,title,lines,color in resources:
        node(key,x,6360,w,title,lines,h=125,color=color,shape="db" if key in {"mysql","minio","milvus","redis"} else "rect")
    # Resource routes stay in inter-panel gutters; dashed and subdued. They are
    # ownership/dependency buses, not direct SQL permission for every upstream node.
    edge("save","mysql",[(1230,4435),(975,4435),(975,5220),(70,5220),(70,6185),(405,6185),(405,6360)],"N2/N3/N4/N5/N6/N7：各域读写事实",(580,6170),kind="resource",color="green")
    edge("upload","minio",[(2340,4645),(2205,4645),(2205,5130),(3050,5130),(3050,6160),(865,6160),(865,6360)],"原文 / 附件读写",(1970,6145),kind="resource")
    edge("k4","milvus",[(2120,2205),(2225,2205),(2225,3208),(3070,3208),(3070,6195),(1290,6195),(1290,6360)],"N6：查询已发布索引 / 构建候选索引",(2520,6190),kind="resource",color="green")
    edge("worker","redis",[(860,4825),(950,4825),(950,5220),(3050,5220),(3050,6208),(1730,6208),(1730,6360)],"事件投递 / 临时状态",(1850,6285),kind="resource")
    edge("k3","embed",[(1790,2003),(2235,2003),(2235,3190),(3095,3190),(3095,6305),(2200,6305),(2200,6360)],"N6 检索 / 构建：向量与重排",(2560,6290),kind="resource",color="gold")
    edge("k6","llm",[(2165,2583),(2255,2583),(2255,3180),(3125,3180),(3125,6328),(2730,6328),(2730,6360)],"授权上下文 → 生成",(2870,6318),kind="resource",color="purple")

    phase("统一入口与权限", "user nginx auth reject page", [960,130,1280,600], "聊天、客服台和管理台都经过统一入口。认证通过不代替后续业务资源校验。", "U01 登录成功，系统知道当前租户与用户；别人的订单不能查。")
    phase("正式消息与会话控制", "auth session router humaninbox", [990,560,1230,570], "先保存本轮输入与控制快照。允许 AI 才交编排；已 HUMAN 的消息通知人工。", "C01 / epoch=7；原始历史只取正式、仍有权限的消息。")
    phase("路由与澄清出口", "session router clarify clarifyresult businessauth kfwrap pending draft", [110,640,2000,710], "根据问题选路径，不是每个请求都经过所有业务模块。人工和已有工作流优先。", "问物流走事实；问材料走知识；问本单能否退走混合；我要申请走确认链。")
    phase("订单 / 物流等真实查询", "businessauth facts needpolicy readresult", [130,1170,820,970], "先校验对象，再读事实。只读问题直接进入 R，模型不能补造物流状态。", "O1001 两个包裹：分别显示状态和更新时间。")
    phase("KF 前半：准备和 FAQ", "kfwrap k0 k1 direct k2 k3 faq", [980,1180,1260,1090], "保持原 KF 主干；确定性或 FAQ 标准答案满足条件可旁路，不强制调用 LLM。", "“退货材料有哪些？”若 FAQ 完整且适用，可直接取标准答案。")
    phase("KF 后半：文档、生成、统一收尾", "k3 k4 k5 empty k6 k7 direct faq", [980,2030,1260,980], "没直出才继续文档检索；证据不足不编造。K7 完成只是 N6 子调用完成。", "无依据时返回无法确认；不能把模型生成结束当平台正式保存成功。")
    phase("混合资格：事实 + 政策 + 批准规则", "facts needpolicy policycall kfwrap k7 rules eligibility", [130,2150,820,840], "N4 顺序调 N5 事实、N6 政策、N5 批准规则，再组合答复；咨询不自动提交。", "演示 P003/RULE003 给出可申请：仍要用户主动申请并明确确认。")
    phase("申请草稿和统一预检", "draft preflight pagewrite", [130,3230,1430,480], "聊天草稿由 N4 管理；页面不建 Workflow。两入口调用同一 N5 预检。", "PF01 绑定 L1×1、理由、申请金额、载荷哈希与有效期。")
    phase("明确确认、幂等提交与结果查询", "preflight confirm submit commandresult result pageresult", [1490,3480,1580,740], "明确确认才提交。变更重新预检；提交超时查原命令，不能新建另一笔。", "CMD01 成功创建 AS001 待审核；不是退款到账。页面结果直接回页面。")
    phase("R：检查 → 正式保存 → 浏览器完成", "result save done outputfailure", [1020,4080,2040,730], "N3 事务保存正式消息与通知后，才发平台完成。最终文本替换草稿，不重复追加。", "KF 已 end 但消息保存失败：只补同一答案发布，不重跑申请。")
    phase("人工本轮：待人工 → 真实受理", "pending ticket ticketack ticketfailure result", [2290,1170,790,650], "先隔离旧 AI，再建单；真实拿到工单 ID 才说已受理，本轮不等客服处理完。", "HD01 重试仍对应 TK01；建单失败不能编造排队位置。")
    phase("人工后续：握手 → 公开回复 → 可靠送达", "humaninbox assign human reply replyworker inbox humandelivered", [2290,1730,790,1470], "N3 确认 HUMAN 后才公开回复。N7 原稿经事件交 N3 正式保存，内部备注不走此线。", "EVT01 已写 M07 但 ACK 丢失：重投仍只显示同一条消息。")
    phase("独立页面入口", "auth page pageread pagewrite upload", [2270,180,810,870], "页面操作直达所属领域；不是所有页面都先走聊天与 RAG。", "售后页与聊天都看同一个 N5 申请，不能各自创建一套事实。")
    phase("反馈与错误归因", "done feedback worker triage fix", [130,4420,830,800], "原始反馈和错误证据经过可靠事件进入责任领域；收到差评不等于已经修复。", "物流数据错交 N5 修链路；不是只改 Prompt 掩盖。")
    phase("知识原文与候选构建", "upload ready build candidate", [1640,4450,1420,1150], "检查原文就绪后才解析、切片、向量化。候选索引不能立即用于正式查询。", "上传 P004 后构建 KB004 候选，线上仍读 KB003。")
    phase("回归、审批、发布和下一轮验证", "triage fix build candidate quality release nextrequest user", [130,5430,2310,730], "独立回归与审批通过才激活兼容版本；失败回修复或保留已验证版本。", "FB01 → 修订 P004 → KB004 回归与审批 → 新 R09 验证改善。")
    phase("底部存储 / 模型及横切保障", "mysql minio milvus redis embed llm", [130,6220,2930,330], "虚线是资源依赖，不是业务处理顺序。各领域只写自己的数据；N9 全程关联脱敏日志与 Trace。", "MySQL 是正式事实；MinIO 原文；Milvus 派生索引；Redis 投递 / 缓存；模型不能直接退款。")


def txt(x,y,s,size=21,color="#e7f0ff",weight=400,anchor="middle"):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{escape(s)}</text>'


def svg():
    group_labels=[]
    content=[f'<svg xmlns="http://www.w3.org/2000/svg" id="panorama" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="map-title"><title id="map-title">V1 全景技术流程图</title>',
        '<defs><pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#1c2c42" stroke-width="1"/></pattern>']
    for key,col in COLORS.items():
        content.append(f'<marker id="arrow-{key}" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="{col}"/></marker>')
    content.extend(['</defs><style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif} .edge{fill:none;stroke-linejoin:round;stroke-linecap:round}.node{cursor:pointer}.node:hover .shape{stroke-width:4}.edge-label{paint-order:stroke fill;stroke:#0c1626;stroke-width:7}</style>',f'<rect width="{W}" height="{H}" fill="#0c1626"/><rect width="{W}" height="{H}" fill="url(#grid)"/>',
        txt(130,55,"智能电商客服平台 V1 · 一张连线全景图",37,weight=700,anchor="start"),
        txt(130,101,"目标设计 / 标准 1.1 · 当前仅 M00.1–M00.4 完成 · 93 条业务用例 NOT_RUN · 原项目与 KF 核心不改",22,COLORS['gold'],anchor="start")])
    for g in groups:
        content.append(f'<rect x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" rx="10" fill="#0e1b2e" stroke="#30425b" stroke-width="2"/>')
        group_labels.append(txt(g['x']+22,g['y']+36,g['title'],25,COLORS[g['color']],700,'start').replace('<text ', '<text style="paint-order:stroke fill;stroke:#0e1b2e;stroke-width:7" '))
        group_labels.append(txt(g['x']+22,g['y']+68,g['subtitle'],19,"#a9bfd7",anchor="start").replace('<text ', '<text style="paint-order:stroke fill;stroke:#0e1b2e;stroke-width:7" '))
    content.append('<g id="edges">')
    for i,e in enumerate(edges):
        dash=' stroke-dasharray="9 6"' if e['kind']=='event' else ' stroke-dasharray="3 7" opacity=".48"' if e['kind']=='resource' else ''
        d=' '.join(('M' if j==0 else 'L')+f'{x},{y}' for j,(x,y) in enumerate(e['points']))
        content.append(f'<path id="edge-{i}" data-from="{e["a"]}" data-to="{e["b"]}" data-kind="{e["kind"]}" class="edge {e["kind"]}" d="{d}" stroke="{COLORS[e["color"]]}" stroke-width="{2 if e["kind"]=="resource" else 2.6}" marker-end="url(#arrow-{e["color"]})"{dash}/>')
    content.append('</g>'+''.join(group_labels)+'<g id="nodes">')
    for n in nodes:
        x,y,w,h,col=n['x'],n['y'],n['w'],n['h'],COLORS[n['color']]
        content.append(f'<g id="{n["id"]}" class="node" tabindex="0" role="button" aria-label="{escape(n["title"],quote=True)}" data-box="{x},{y},{w},{h}"><title>{escape(n["title"]+"；"+n["detail"])}</title>')
        if n['shape']=='decision':
            d=f'M{x+26},{y} H{x+w-26} L{x+w},{y+h/2} L{x+w-26},{y+h} H{x+26} L{x},{y+h/2} Z'
            content.append(f'<path class="shape" d="{d}" fill="#302737" stroke="{col}" stroke-width="2.5"/>')
        else:
            content.append(f'<rect class="shape" x="{x}" y="{y}" width="{w}" height="{h}" rx="{18 if n["shape"]=="db" else 5}" fill="#13253b" stroke="{col}" stroke-width="2"/>')
        yy=y+(h-(28+len(n['lines'])*27))/2+21
        content.append(txt(x+w/2,yy,n['title'],23,col,700))
        for j,line in enumerate(n['lines']):
            content.append(txt(x+w/2,yy+30+j*27,line,20))
        content.append('</g>')
    content.append('</g><g id="labels">')
    for e in edges:
        if e['label'] and e['at']:
            x,y=e['at']
            content.append(f'<text class="edge-label {e["kind"]}" x="{x}" y="{y}" fill="{COLORS[e["color"]]}" font-size="19" text-anchor="middle">{escape(e["label"])}</text>')
    content.append('</g>')
    content.append(txt(130,6575,"N9 横切：Trace / 脱敏日志 / 指标 / 告警；领域审计随领域事务持久化。备份恢复、权限撤销、对账与故障验收仍依四份标准执行。",21,"#a9bfd7",anchor="start"))
    content.append('</svg>')
    return ''.join(content)


def main():
    build_data()
    drawing=svg()
    (OUT/(STEM+'.svg')).write_text(drawing,encoding='utf-8')
    payload=dict(width=W,height=H,nodes=nodes,edges=edges,phases=phases)
    (OUT/'source'/'panorama-manifest.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    template='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V1 全景技术流程图 · 逐步讲解</title><style>
*{box-sizing:border-box}body{margin:0;background:#0c1626;color:#e8f2ff;font:15px/1.6 "Microsoft YaHei",sans-serif}header{padding:14px 20px;border-bottom:1px solid #344963;background:#111e32}h1{font-size:23px;margin:0 0 3px}p{margin:4px 0;color:#b2c8df}.tools{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin-top:9px}button,select,a{font:inherit;color:#96dfe9;background:#192d44;border:1px solid #426080;border-radius:5px;padding:5px 10px;text-decoration:none;cursor:pointer}button:hover,a:hover{border-color:#f5bd62}select{max-width:360px}output{color:#f5bd62;min-width:55px}progress{height:8px;width:120px}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 286px;height:calc(100vh - 164px);min-height:480px}#viewport{overflow:auto;position:relative;overscroll-behavior:contain}#sheet{padding:35px;width:max-content}#sheet svg{display:block;max-width:none;height:auto}aside{padding:16px;background:#102034;border-left:1px solid #344963;overflow:auto}h2{font-size:18px;color:#6bd4e5;margin:0 0 9px}aside .example{padding:10px;border-left:3px solid #f5bd62;background:#2b2931;color:#f8d18c;margin:14px 0}small{font-size:12px;color:#9fb4cb}.hint{font-size:12px;margin-top:7px}.node.selected .shape{stroke:#fff!important;stroke-width:5}.guided .node:not(.active){opacity:.28}.guided .edge:not(.active){opacity:.12}.guided .edge.active{opacity:1;stroke-width:4}.guided .node.active .shape{stroke-width:3.5}.guided .edge-label{opacity:.55}.hide-resources .resource{display:none}details{margin-top:18px;font-size:13px}summary{cursor:pointer;color:#a6dbea}@media(max-width:850px){.workspace{grid-template-columns:1fr;height:calc(100vh - 210px)}aside{display:none}header{padding:10px}h1{font-size:19px}select{max-width:230px}.hint{display:none}}
</style></head><body><header><h1>智能电商客服 V1 · 全景技术流程图</h1><p>一张图连通：请求 → 路由 → 业务 / KF / 人工 → 正式回复 → 反馈、知识与发布闭环。</p>
<div class="tools"><button id="prev">上一步</button><select id="phases" aria-label="讲解步骤"></select><button id="next">下一步</button><output id="counter"></output><progress id="progress"></progress><button id="all">全图</button><button id="fit">适应宽度</button><button id="minus" aria-label="缩小">−</button><output id="zoom"></output><button id="plus" aria-label="放大">＋</button><button id="actual">100%</button><label><input id="resources" type="checkbox" checked>资源依赖</label><a href="__STEM__.png" download>高清 PNG</a><a href="__STEM__.svg" download>SVG</a></div>
<p class="hint">讲解顺序不等于单次请求的执行顺序：按路由择一。实线＝处理 / 返回；长虚线＝异步；点虚线＝资源依赖。点击节点看说明。示例为虚构 DEMO。</p></header>
<div class="workspace"><main id="viewport" aria-label="可缩放完整流程图"><div id="sheet">__SVG__</div></main><aside><h2 id="detail-title"></h2><p id="detail"></p><p class="example" id="example"></p><small>先沿亮色箭头读当前步骤，再点“下一步”。全图按钮取消高亮；原图各分支仍在同一张画布上。</small><details><summary>完成口径与资料</summary><p>M00.1–M00.4 完成；93 条业务验收仍 NOT_RUN。本次只调整图示，不改 KF 核心和平台标准。</p><p>事实归 N5；正式会话归 N3；编排归 N4；知识归 N6；人工归 N7；N8 只执行所属领域任务。</p><p><a href="../../implementation-standards/v1/README.md">四份实施标准</a></p><p><a href="V1分层流程与示例.html">上一版节点详解</a></p></details></aside></div>
<script>const DATA=__DATA__;const svg=document.querySelector('#panorama'),viewport=document.querySelector('#viewport'),select=document.querySelector('#phases');let scale=1,current=0;
DATA.phases.forEach((p,i)=>{const o=document.createElement('option');o.value=i;o.textContent=(i+1)+'. '+p.title;select.append(o);});
function resize(v,cx,cy){const old=scale;const pointX=cx??(viewport.scrollLeft+viewport.clientWidth/2-35)/old,pointY=cy??(viewport.scrollTop+viewport.clientHeight/2-35)/old;scale=Math.max(.18,Math.min(2,v));svg.style.width=(DATA.width*scale)+'px';document.querySelector('#zoom').value=Math.round(scale*100)+'%';viewport.scrollTo({left:Math.max(0,pointX*scale+35-viewport.clientWidth/2),top:Math.max(0,pointY*scale+35-viewport.clientHeight/2),behavior:'instant'});}
function showStep(i){current=Math.max(0,Math.min(DATA.phases.length-1,i));const p=DATA.phases[current],ids=new Set(p.ids);select.value=current;svg.classList.add('guided');svg.querySelectorAll('.node').forEach(n=>{n.classList.toggle('active',ids.has(n.id));n.classList.remove('selected');});svg.querySelectorAll('.edge').forEach(e=>e.classList.toggle('active',ids.has(e.dataset.from)&&ids.has(e.dataset.to)));document.querySelector('#detail-title').textContent=p.title;document.querySelector('#detail').textContent=p.explanation;document.querySelector('#example').textContent='示例：'+p.example;document.querySelector('#counter').value=(current+1)+' / '+DATA.phases.length;document.querySelector('#progress').max=DATA.phases.length;document.querySelector('#progress').value=current+1;document.querySelector('#prev').disabled=current===0;document.querySelector('#next').disabled=current===DATA.phases.length-1;const[x,y,w,h]=p.bounds;resize(Math.min(1.5,(viewport.clientWidth-60)/w,(viewport.clientHeight-60)/h),x+w/2,y+h/2);}
document.querySelector('#prev').onclick=()=>showStep(current-1);document.querySelector('#next').onclick=()=>showStep(current+1);select.onchange=()=>showStep(Number(select.value));document.querySelector('#all').onclick=()=>{svg.classList.remove('guided');svg.querySelectorAll('.selected').forEach(n=>n.classList.remove('selected'));resize((viewport.clientWidth-70)/DATA.width,DATA.width/2,viewport.clientHeight/2/((viewport.clientWidth-70)/DATA.width));viewport.scrollTop=0;};document.querySelector('#fit').onclick=()=>resize((viewport.clientWidth-70)/DATA.width);document.querySelector('#actual').onclick=()=>resize(1);document.querySelector('#plus').onclick=()=>resize(scale+.15);document.querySelector('#minus').onclick=()=>resize(scale-.15);document.querySelector('#resources').onchange=e=>svg.classList.toggle('hide-resources',!e.target.checked);
function inspect(id){const n=DATA.nodes.find(n=>n.id===id);svg.querySelectorAll('.selected').forEach(el=>el.classList.remove('selected'));document.getElementById(id).classList.add('selected');document.querySelector('#detail-title').textContent=n.title;document.querySelector('#detail').textContent=n.detail||n.lines.join('；');document.querySelector('#example').textContent=n.example?'示例：'+n.example:'落点说明：本节点只代表目标设计中的职责，不代表已完成运行验收。';}
svg.querySelectorAll('.node').forEach(n=>{n.onclick=()=>inspect(n.id);n.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();inspect(n.id);}};});window.addEventListener('resize',()=>showStep(current));showStep(0);
</script></body></html>'''
    (OUT/TITLE).write_text(template.replace('__STEM__',STEM).replace('__SVG__',drawing).replace('__DATA__',json.dumps(payload,ensure_ascii=False).replace('</','<\\/')),encoding='utf-8')
    print(f'{len(nodes)} nodes / {len(edges)} edges / {len(phases)} guided steps; {W} x {H}.')


if __name__=='__main__':
    main()
