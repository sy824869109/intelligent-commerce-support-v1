"""Build offline, code-native V1 review diagrams; never access a live service.

Hierarchy is presentation only: overview -> detailed flow -> per-node example.
The original KF pipeline and the platform's accepted domain ownership stay intact.
All example identifiers, policies and amounts are synthetic DEMO fixtures.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
import re
import unicodedata

OUT = Path(__file__).resolve().parents[1]
W = 1200
C = {"blue": "#65cbe0", "gold": "#f1be63", "green": "#74d7ad", "red": "#f1999f", "purple": "#c1adff"}
FLOWS = []


def step(key, title, owner, incoming, action, outgoing, persist, example, *, side=None, link=None, phase=None, color="blue", onward="继续向下"):
    return dict(key=key, title=title, owner=owner, incoming=incoming, action=action,
                outgoing=outgoing, persist=persist, example=example, side=side,
                link=link, phase=phase, color=color, onward=onward)


def flow(key, number, title, intro, nodes, *, example, parents="V1 总流程"):
    FLOWS.append(dict(key=key, number=number, title=title, intro=intro,
                      nodes=nodes, example=example, parents=parents))


def content():
    flow("overview", "06", "第 1 层 · 一条主干看全程", "从一个客户请求向下读。右侧是离开主路的条件，不是必须逐个经过的服务。", [
        step("A01", "用户发起一次请求", "客户浏览器 / 客服台 / 管理台", "问题文本，或页面操作；登录凭据", "区分聊天入口与页面入口，不把页面申请伪造成聊天。", "聊天 → A02；页面 → 图 13；知识上传 → 图 12", "此时尚无服务端业务结果。", "客户问：O1001 的杯子裂了，可以申请退货吗？", side=("其他入口", "页面申请见图 13；管理台知识处理见图 12。", "page"), phase="① 接收：谁在操作，允许做什么"),
        step("A02", "统一入口与身份权限", "N1 Nginx → N2 Gateway / IAM", "请求、身份凭据、租户和目标资源", "校验登录、租户、角色、限流及输入；业务域再校验归属。", "已认证 actor / tenant / request_id / trace_id", "N2 保存自己拥有的安全审计；不写订单。", "DEMO 租户 T01 的 U01 登录成功。", side=("不通过 → 在入口结束", "未登录、越权或超限：返回安全错误，不继续业务执行。", None)),
        step("A03", "保存本轮输入，取得会话控制资格", "N3 Conversation → N4 Orchestration", "授权身份、conversation_id、消息幂等键", "N3 保存输入和控制快照；允许 AI 时预留资格，N4 建 Run。", "正式历史快照、control_epoch；适用时有 run_id", "N3：消息 / 控制；N4：Run；不在锁中等待模型。", "C01 / R01 / epoch=7；当前问句与历史分开。", side=("已经人工接管", "保存客户消息并通知人工；不再启动可公开答复的 AI Run。", "human")),
        step("A04", "逐级判断本轮应走哪条路", "N4 确定性编排", "本轮问题 + 控制模式 + Workflow + 权限", "先安全与人工，再已有流程，再补充信息，最后选业务路径。", "CLARIFY / READ / KNOWLEDGE / MIXED / COMMAND 等", "N4 保存路由原因和工作流版本。", "既问具体订单，又问政策 → MIXED。", link="routing", phase="② 判断：先排除不能做，再决定怎样做", color="gold"),
        step("A05", "只执行被选中的分支", "N4 协调 N5 / N6 / N7", "确定的路由、最少业务参数、授权范围", "读业务 → N5；知识 → N6/KF；混合 → N5→N6→N5。", "带事实 / 来源 / 状态的领域结果，不是模型自由承诺。", "N5 业务；N6 知识；N7 工单，各写自己的数据。", "查 O1001 → 检索 P003 → N5 判定可提交申请。", link="mixed", side=("人工分支", "先真实建单受理；人工稍后回复是另一条异步流程。", "human"), phase="③ 执行：子图内部再逐步展开"),
        step("A06", "校验结果，正式保存，再通知完成", "N4 检查 → N3 正式消息 → N2 / N1", "执行结果、来源、Run / epoch 和关联业务 ID", "检查权限与输出；N3 事务校验资格、写消息和通知 Outbox。", "message.committed 后才 run.completed", "正式消息只认 N3；KF 内部 end 不是平台完成。", "M02：可申请，仍需确认；没有自动创建退货单。", link="publish", color="green"),
        step("A07", "用户继续、确认、转人工或评价", "浏览器 → 所属领域", "新的用户动作，不沿用旧动作的授权", "确认进入新一轮；评价单独保存；断线重连补查正式结果。", "新一轮 A01，或反馈事件，或人工接管请求", "N3 反馈；N4 草稿确认；N5 申请；N7 人工记录。", "U01 点明确确认后才走申请；点差评则进入治理。", side=("不是全部都要做", "追问 / 申请 / 人工 / 评价是不同后续动作，可选其一或结束。", None), phase="④ 后续：本轮完成后，才发生新动作"),
        step("A08", "反馈进入修复与验证闭环", "各领域 Outbox → N8 → 责任领域", "评价、错误、人工纠正及原始消息 / 版本引用", "归因 → 审核 → 修复 → 独立回归 → 审批发布。", "通过门禁的版本；失败仍留候选态", "原始反馈不被覆盖；修复和发布留审计。", "P003 表述有歧义 → 修订候选 P004，不直接上线。", link="closure", color="purple"),
        step("A09", "下一次请求验证改进是否有效", "新请求 → N4 / N6 / N5", "新授权快照 + 当前可用且兼容的已发布版本", "读取新版本服务，再采集效果；失败可回到已验证版本。", "重新从 A01 开始，而不是复活旧 Run", "保留发布版本、回归证据与新请求关联。", "R09 使用 KB004；回归后同类问题得到清楚解释。", color="green"),
    ], example="示例主线：咨询能否申请 → 明确确认 → 创建待审核申请。模型没有执行退款。")

    flow("routing", "07", "第 2 层 · 路由按优先级逐关判断", "从 B01 向下；一旦命中右侧出口，就不继续做下一项路由判断。", [
        step("B01", "接收授权输入与控制快照", "N3 → N4", "问题、会话模式、Workflow、历史授权范围", "只消费本轮有效输入；历史问题不是新的执行授权。", "本轮可判定的信息；身份失效退回 N2 重新授权", "N4 路由记录绑定 Run / epoch。", "问 O1001 能否退货；AI 模式，无活动 Workflow。", phase="第一优先级：安全 / 人工 / 控制"),
        step("B02", "是否必须拒绝，或要求 / 需要人工？", "N4；控制由 N3 持有", "安全规则、人工请求、风险、会话模式", "被禁止的操作拒绝；人工请求优先；HUMAN 模式不启动 AI。", "未命中 → B03；命中 → 右侧对应出口", "控制改变写 N3；人工受理记录写 N7。", "“帮我退钱”不授权自动扣付；“找人工”进入人工链。", side=("命中：离开路由主干", "禁止操作 → REFUSE → 图 10；人工 → 图 11；HUMAN 直接人工处理。", "human"), color="gold", onward="均未命中，向下"),
        step("B03", "是否在已有业务工作流中？", "N4 Workflow", "current_workflow / version / 待确认摘要", "优先处理取消、修改、继续或明确确认；改内容即废止旧确认。", "无活动流程 → B04；有流程 → 相应步骤", "N4 更新工作流版本；已提交命令另查 N5。", "“不退了，改换货” → 作废原退货确认，再预检。", side=("命中：不是重新分类", "待确认 → 图 08 T08；已提交且结果未知 → 查原 command_id。", "mixed"), color="gold", onward="没有活动流程，向下"),
        step("B04", "目标或必要信息是否缺失 / 冲突？", "N4；授权候选由 N5 提供", "本轮涉及的订单、商品行、数量、目的", "业务问题缺目标先澄清；纯政策问答不强索取订单号。", "信息充分 → B05；不足 → CLARIFY → 图 10", "N4 只保存获授权的收集槽位。", "“帮我退那个”且有两个订单 → 请用户选择，不猜订单。", side=("是：本轮只问清楚", "返回合法候选或追问；等下一轮补充，不执行申请。", "publish"), color="gold", onward="信息充分，向下"),
        step("B05", "是否只是查询业务事实？", "N4 → N5 Commerce", "已授权订单 / 商品 / 包裹 ID", "只读真实事实，必要时选择具体商品行或包裹。", "是 → COMMERCE_READ → N5 结果 → 图 10", "只读不创建售后；N5 保留查询审计。", "“O1001 物流到哪了？” → 分包裹状态和更新时间。", side=("是：读完即收口", "数据不可用就明确说明；不可用模型补一个物流状态。", "publish"), phase="第二优先级：明确业务性质", color="gold", onward="不是单纯查事实，向下"),
        step("B06", "是否只问通用知识或政策？", "N4 → N6 Knowledge / KF", "问题 + 授权知识域 + 正式历史快照", "查询已发布适用知识；不据通用政策判定具体订单资格。", "是 → KNOWLEDGE → 图 09 → 图 10", "N6 诊断不替代 N3 正式历史。", "“退货需要准备什么？” → 回答材料和来源。", side=("是：只给知识答复", "没有资格判定，也没有业务写入。", "kf"), color="gold", onward="不是单纯问知识，向下"),
        step("B07", "是否在咨询具体对象的政策或资格？", "N4 顺序协调", "已选定对象 + 政策 / 资格咨询", "咨询时先 N5 事实，再 N6 政策、N5 规则；明确请求办理走 B08。", "是 → MIXED → 图 08 T01–T06 → 图 10", "资格由 N5 判断，N6 不拥有订单审批权。", "“O1001 的杯子裂了，可以申请退货吗？”", side=("是：混合路径", "先回答是否可申请；不要把咨询当作确认。", "mixed"), color="gold", onward="不是混合咨询，向下"),
        step("B08", "是否请求受支持的受控业务操作？", "N4 → N5 统一命令端口", "动作、目标、业务范围模式及必要材料", "在支持范围内收集 → 预检 → 明确确认 → 同键提交。", "是 → BUSINESS_COMMAND → 图 08 T07–T11", "N4 确认意图；N5 预检、命令及业务结果。", "“我要申请退货” → 展示摘要，等用户明确确认。", side=("是：不能跳过确认", "LIVE / DEMO 明示；HUMAN_ONLY 转人工；UNSUPPORTED 不支持。", "mixed"), color="gold", onward="仍不匹配，向下"),
        step("B09", "兜底：澄清、真实人工或明确不支持", "N4 → N3 / N7", "未识别、证据矛盾或超出支持范围的问题", "不给虚构结论；提供具体可选的下一步。", "CLARIFY / HUMAN / REFUSE；不静默执行", "记录失败归因；没有受理回执不称已受理。", "“把积分转成现金”不在 V1 自动办理范围 → 说明边界。", link="publish", color="red"),
    ], example="例：缺订单 → B04 澄清；只查物流 → B05；问退货材料 → B06；问本单能否退 → B07。")

    flow("mixed", "08", "第 2 层 · 例 1：售后咨询到受控申请", "T01–T06 是第一轮咨询；T07–T11 是用户主动申请 / 确认后的新阶段，不会在问完后自动连跑。", [
        step("T01", "确认问题与业务对象", "N4 → N5", "T01 / U01：O1001 中 L1 杯子有裂纹，能申请退货吗？", "识别 MIXED；N5 校验订单归属，必要时让用户选商品行。", "授权对象 O1001 / L1 / qty=1", "N4 本轮 R01；N5 仍是业务事实所有者。", "所有租户、订单、政策与金额都是虚构 DEMO 数据。", phase="第一轮：能否申请？只咨询，不写申请"),
        step("T02", "读取带版本的事实", "N4 调 N5", "授权对象、当前用户", "查询签收、商品、数量、已有售后、销售区域和渠道。", "facts_version=F12；已签收 2 天，可申请数量 1", "N5 返回时间戳 / 事实版本；不返回无关个人资料。", "L1 数量 1，未占用售后；渠道标记 DEMO。", side=("归属失败或多对象", "越权不暴露资源；目标有歧义回图 07 B04 澄清。", "routing")),
        step("T03", "带最小属性查适用政策", "N4 调 N6 → KF", "商品类别、区域、适用时间依据、授权知识域", "以正式历史适配与固定版本检索；见图 09 K0–K7。", "P003 / KB003；来源、适用范围、有效期", "N6 保存检索诊断，不保存 / 决定订单资格。", "虚构 P003：签收 14 天内可提交破损申请，仍需审核。", link="kf", side=("无证据或政策冲突", "返回 UNKNOWN / REVIEW_REQUIRED；不生成“肯定能退”的承诺。", "human")),
        step("T04", "用批准规则判定申请资格", "N4 再调 N5", "F12 事实 + P003 依据 + 批准规则 RULE003", "N5 核对适用时间、范围、规则版本和剩余数量。", "ELIGIBLE：本例只表示符合提交申请的条件", "规则执行与资格结果归 N5；不是模型投票。", "可进入申请流程 ≠ 缺陷审核通过 ≠ 钱款退回。", side=("其余资格结果", "INELIGIBLE 解释依据；REVIEW_REQUIRED 转人工；UNKNOWN 不下结论。", "human")),
        step("T05", "组织明确而有边界的答复", "N4", "事实 + 政策引用 + N5 资格 + 下一步", "高风险输出先缓冲检查；只解释可申请和仍待确认。", "“本单可提交申请；请核对信息，申请仍需审核。”", "N4 保存本轮结果；此时没有售后申请单。", "不说“已经退款”，也不自动调用提交接口。"),
        step("T06", "第一轮正式结束", "N3 → 客户端", "待发布答复、引用、R01 / epoch", "走图 10 正式发布，客户端取得 M02。", "本轮结束；用户不继续则停在这里", "N3 正式消息 M02；没有 command_id / after_sale_id。", "用户稍后点“我要申请”才开始下方第二阶段。", link="publish", color="green", onward="仅当用户主动申请时，进入新阶段"),
        step("T07", "收集草稿并取得 N5 预检", "N4 Workflow → N5 preflight", "动作、L1、数量、理由、READY 附件引用", "N5 重验权限和当前事实，签发绑定载荷与版本的 preflight_id。", "PF01；申请摘要：L1 ×1，申请金额 19900 分 CNY", "N5 持有预检；N4 W01/v1 绑定预检与确认凭据。", "199.00 元是演示申请金额，非承诺最终退款金额。", phase="第二阶段：申请草稿 → 用户明确确认", side=("预检失败", "超数量、状态变更、附件未就绪：先修正，再生成新摘要。", None)),
        step("T08", "展示同一份摘要，等待明确确认", "N4 / 浏览器", "PF01、W01/v1、载荷哈希、有效期、申请摘要", "展示目标 / 数量 / 理由 / 金额 / 后果；不得默认确认。", "只有“确认提交这份申请”才消耗当前确认", "N4 保存确认依据；用户、预检与工作流版本绑定。", "“我再看看” → 不提交；“改成换货” → 原确认失效。", side=("修改 / 过期 / 取消", "修改或过期 → 回 T07；未提交时取消草稿；已提交另查原命令。", None), color="gold"),
        step("T09", "固定命令标识，提交同一载荷", "N4 → N5 统一提交端口", "有效确认 + PF01 + 原载荷 + stable command_id", "N4 事务写确认消耗、命令意图和 Outbox；N5 再校验并幂等接受。", "CMD01；同预检只对应一个领域命令", "N4 保存意图；N5 保存命令和领域效果，非跨域事务。", "重复点击或重投仍查 / 用 CMD01，不新建另一申请。", side=("状态 / 金额变化", "N5 拒绝过时预检；回 T07 重新展示并确认，不能静默改金额。", None)),
        step("T10", "读取真实领域结果", "N5 → N4", "CMD01 的权威结果", "命令执行成功只表示创建了申请；关联实际售后单。", "CMD01=SUCCEEDED；AS001=待审核（展示语义）", "N5：申请与命令结果；售后状态枚举由业务合同冻结。", "应答“申请 AS001 已提交，待审核”，不是“退款到账”。", side=("超时，结果未知", "展示 RESULT_UNKNOWN；查同 CMD01 / 对账。停止生成不等于撤销申请。", None), color="green"),
        step("T11", "提交轮收口，后续查询同一申请", "N4 → 图 10；页面查询走 N2 → N5", "AS001 / CMD01、真实状态、关联 Run", "N3 保存本轮正式结果；刷新或重连查询已有事实。", "用户在聊天和售后页看见同一 AS001", "N3 持有答复，N5 持有售后事实；两者不能互相代替。", "审核 / 寄回 / 验收 / 退款以后续已接入事实为准。", link="publish", color="green"),
    ], example="E1：T01/U01、O1001/L1、P003、PF01、CMD01、AS001 是一组完整的虚构演示关联，不是实际 API 合同。")

    flow("kf", "09", "第 3 层 · KF 原核心逐步展开", "只展开 N6 子调用；不改变 KF Stage 0–7 顺序。右侧是已有旁路，明确汇入同一个 K7。", [
        step("G00", "N6 授权包装与请求级历史适配", "N4 → N6", "当前问题 + 最小业务属性 + N3 正式历史快照", "校验租户、知识可见性、场景，绑定已发布版本和请求级 History Adapter。", "授权 Query Context；只向模型发送必要信息", "读历史只取 N3 快照；不临时修改共享单例 history。", "Q：破损申请要什么材料？知识域 T01，版本 KB003。", phase="平台包装：权限先于检索 / 缓存 / 模型"),
        step("K0", "创建 KF 查询上下文", "KF Stage 0", "问题、场景、检索权限、会话和 Trace", "建立本次 Pipeline 状态及版本绑定。", "本次 context，进入 K1", "诊断关联 tenant / run；不写平台正式消息。", "同一次 R02 只用已授权、兼容的 KB003。", phase="KF 原有主干：从 K0 向下"),
        step("K1", "低成本路由", "KF Stage 1", "当前问题和场景配置", "判断确定性直答或 FAQ 精确命中，否则准备检索。", "继续检索 → K2；确定直答 → K7", "保留路由诊断；不产生订单资格。", "若“营业时间”精确命中可直接取标准答案。", side=("直答出口 → K7", "跳过 K2–K6；仍走统一收尾，再由平台校验发布。", None), color="gold", onward="需要检索，向下"),
        step("K2", "准备检索", "KF Stage 2 + 请求级 History Adapter", "当前问句 + 授权正式历史 + 场景", "意图、按需改写、查询变体、来源过滤、检索计划与 Prompt Profile。", "检索计划和查询；不重复注入当前问题", "只读授权快照；撤权后旧摘要 / 缓存失效重建。", "“要准备哪些？”结合正式前文改写为破损申请材料。"),
        step("K3", "FAQ 检索与直出判断", "KF Stage 3", "检索计划、查询、可见知识范围", "按计划混合召回，按配置重排，判断能否用标准答案直出。", "不满足直出 → K4；满足 → K7", "读 Milvus；调用向量 / 可选重排模型。", "已有完整且适用的材料清单，满足条件时直接返回。", side=("FAQ 直出 → K7", "跳过后续文档检索和 LLM；不是跳过来源授权。", None), color="gold", onward="未直出，按计划继续"),
        step("K4", "文档召回与重排", "KF Stage 4", "查询变体、过滤条件、候选片段", "按原检索计划检索 / 重排；计划可关闭对应分支。", "文档片段、来源元数据、检索分数", "Milvus 是派生索引；原文归 MinIO，元数据归 N6。", "找到 P003 的材料段落及适用范围，不是整库原文。"),
        step("K5", "整理生成上下文，检查证据", "KF Stage 5", "FAQ / 文档候选与上下文预算", "合并、裁剪、组织证据与引用；没有足够证据则明确无法确认。", "证据可用 → K6；证据不足 → K7", "不允许以“看起来合理”替代证据。", "材料说明只覆盖照片时，不补造“必须三张”的要求。", side=("证据不足 → K7", "不编造答案；返回无法确认及下一步，由平台决定人工等处理。", None), color="gold", onward="证据可用，向下"),
        step("K6", "LLM 生成及原有后处理", "KF Stage 6 / LangChain", "授权证据、Prompt、模型配置", "生成文本并做引用等后处理；平台普通咨询可受控预览，高风险缓冲。", "候选答案和引用，不是正式会话成功", "LLM 不持有交易执行权限；引用检查不保证所有事实正确。", "通用材料说明可预览；订单资格 / 金额承诺不先流出。"),
        step("K7", "KF 统一收尾", "KF Stage 7 / finish_success；异常 finish_error", "主路或直答 / FAQ / 证据不足旁路的子结果", "保留诊断历史写入和 Trace；经包装层归一化 end / error。", "子调用结果 → N4；MIXED 回图 08 T04，纯知识去图 10", "add_turn 写隔离诊断域，不回灌下一轮正式历史。", "KF end 已发生，但 N3 未保存时浏览器仍不能显示正式完成。", side=("任一步依赖故障", "归一化失败；无真实降级结果则失败，不能把 error 转成功 end。", "publish"), color="green"),
    ], example="E2：普通材料问题可 FAQ 直出；冷门且无证据的问题明确无法确认。K7 是同一节点，不新造旁路服务。", parents="总流程 A05 → N6 子调用")

    flow("publish", "10", "第 2 层 · 所有 AI 分支怎样正式收口", "区分三个时点：领域完成 / KF 完成 → 平台正式保存 → 客户端收到。它们不是同一个成功。", [
        step("F01", "接收真实结果或明确失败", "N4", "N5 事实 / 命令、N6 子结果、N7 受理或澄清文本", "归一化为有来源与实际状态的结果；不把 KF error 改为成功。", "待检查结果，或明确失败 / 真实降级结果", "N4 记录执行状态；领域事实仍归各领域。", "CMD01 成功创建 AS001；不代表 AS001 审核通过。", phase="第一道门：这个结果是否真实可发布"),
        step("F02", "复核权限、控制和输出安全", "N4；N3 最终提交守卫", "答案、来源、Run、epoch、当前授权版本", "重验引用可见性、字段脱敏和当前发布资格。", "可发布 → F03；旧 Run / 越权结果 → 抑制或失败", "执行终态和 publication_status 分开记录。", "R01 已被 R02 取代：旧答案不再正式发布。", side=("旧结果 / 权限撤销", "SUPPRESSED 或安全失败；不能复活旧 Run，也不能回灌其草稿。", None), color="gold"),
        step("F03", "区分预览与最终文本", "N4 → 平台流适配", "受控 token 或已缓冲的高风险结果", "普通 answer.delta 仅草稿；高风险先仅发 progress，检查后提交完整结果。", "候选最终文本；尚未宣称本轮正式完成", "delta 不要求逐 token 持久化；没有恢复游标就补快照。", "资金 / 资格场景不先发送全文再事后遮罩。"),
        step("F04", "同一事务保存正式消息和通知", "N3 Conversation", "最终文本、引用、关联 ID、发布幂等键", "事务内校验 Run / epoch / 唯一键，写正式消息和通知 Outbox。", "正式 message_id + message_seq + 发布回执", "N3 MySQL 是正式会话权威，不以 Redis 或 KF 历史替代。", "M04 关联 R03 / CMD01 / AS001，只生成一条正式答复。", side=("保存失败 / 回执丢失", "查同一发布结果；只补偿同一答案发布，不重新运行 KF 或退款申请。", None)),
        step("F05", "持久化之后发送平台完成事件", "N3 / N4 → N2 → N1 → 浏览器", "正式保存凭据及授权通知流", "发 message.committed，再完成 run.completed；KF end 只代表子调用结束。", "客户端取得正式 MessagePart / 来源 / 状态", "SSE 持久游标由平台定义，不复用 Redis ID / token_seq。", "先收到 M04 的正式版本，再显示“本轮完成”。", phase="第二道门：消息确实保存，才通知完成", color="green"),
        step("F06", "正式消息替换草稿并支持恢复", "授权浏览器 / N3", "message_id、正式全文、持久游标或会话快照", "最终全文替换草稿；重连重新鉴权、补事件或查 snapshot，按 ID 去重。", "一致的聊天记录；断连不重复办理业务", "客户端不是权威存储；无法补 token 时恢复正式快照。", "同一 M04 重到两次仍只显示一次，不把全文追加成双份。", side=("客户端断线", "申请可以已经成功；重连查 CMD01 / AS001，不自动再提交。", None), color="green"),
        step("F07", "下一轮只读取正式授权上下文", "N3 → N6 请求级适配", "当前仍可访问的正式消息 / 摘要", "排除私密备注、未发布答案与失败草稿；当前问句单独传入。", "新 Run 的正式快照；回图 06 A01", "摘要绑定源消息和权限版本；诊断历史不自动合入。", "即便 KF 写了 R01 诊断，若未正式发布，下轮也不读该答案。", color="purple"),
    ], example="E3：N5 已建单而浏览器超时，恢复应显示已有 AS001；不能因为没看到回复就新建一单。")

    flow("human", "11", "第 2 层 · 例 2：从找人工到真实回复", "分成“立即受理”和“稍后人工处理”。创建工单不是客服已经接管，更不是业务已办结。", [
        step("H01", "用户要求人工", "N4 → N3", "“我要找人工”，当前 C01 / epoch", "先让 N3 进入 HANDOFF_PENDING，递增控制代次，隔离旧 AI 发布。", "稳定 handoff_request_id=HD01，进入待接管", "N3 保存模式；N4 失效未用确认，已提交命令另行对账。", "正在生成的旧退款建议不再作为新正式答案发出。", phase="本轮同步：先管住 AI，再真实受理"),
        step("H02", "幂等创建或关联人工工单", "N4 → N7 Ticket", "HD01、授权公开上下文和用户诉求", "N7 保存受理工单并返回真实 ticket_id；重复请求关联原工单。", "TK01 + 实际受理状态", "N7 持有工单；上下文按最小权限引用。", "重复点“找人工”仍关联 TK01。", side=("创建失败", "只能显示尚未成功受理；重试原 HD01，不虚构排队号或等待时长。", None)),
        step("H03", "保存受理说明，本轮结束", "N4 → N3 → 图 10", "TK01 和当前真实受理状态", "经允许的接管受理发布路径保存系统说明；不是旧 AI 继续自由生成。", "客户看见“已受理，等待接管”，本轮结束", "N3 保存受理消息；N7 保存工单事实。", "此时允许等待或留言，不声称客服已在线处理。", link="publish", color="green", onward="之后客服上线认领，才发生下方事件"),
        step("H04", "客服认领，取得唯一有效分配", "客服台 → N2 → N7", "客服权限、TK01 版本和分配请求", "N7 原子检查竞争，只有一人获得有效 assignment。", "ASSIGN01，activation=PENDING", "N7 保存分配事实；不是直接修改 N3 会话表。", "客服 A 与 B 同时抢单，只能一个有效。", phase="后续异步：认领 → 握手 → 开放回复"),
        step("H05", "N3 确认 HUMAN 后才开放回复", "N7 → N3 CAS → N7", "ASSIGN01、expected_epoch、目标模式", "版本化握手；N3 确认 HUMAN 后，客服台才启用公开回复。", "真实接管成功；activation=ACTIVE", "N3 控制事实；N7 分配同步状态，各自幂等。", "响应丢失查同 ASSIGN01，不再建第二份分配。", side=("握手未确认", "仍显示待激活；同分配查询 / 重试，禁止先公开回复。", None), color="gold"),
        step("H06", "客服提交公开回复或内部备注", "N7", "当前有效分配、回复正文、公开性", "重新验证权限；公开回复与 Outbox 同事务保存。", "REPLY01 + EVT01；内部备注不生成客户公开事件", "N7 持有回复原稿、内部备注和人工纠错。", "“请补充破损照片”公开；内部风控备注不发给客户。", side=("发生转派", "转派后旧客服新写入被拒；转派前已合法提交的公开回复可继续投递。", None)),
        step("H07", "Outbox 投递，Worker 转交所属服务", "N7 Relay → Redis Streams → N8 → N3", "已提交的公开事件 EVT01", "按原事件 ID 重试；验证来源、公开性和原始提交凭据。", "交 N3 幂等处理；还不能提前 ACK", "Redis 是投递层；N8 不直接改 N3 / N7 表。", "Worker 重启后可重新认领 EVT01。", phase="送达：跨领域至少一次投递，而非直接推一条文本"),
        step("H08", "N3 保存正式人工消息后 ACK", "N3 Inbox 处理器 → N8", "EVT01 / REPLY01、当前收件人权限", "同事务写 Inbox、正式消息和通知 Outbox；持久成功再 ACK。", "M07；重复 EVT01 返回原结果", "N3 正式消息 M07；N7 原稿 REPLY01 保留署名。", "效果已保存而 ACK 丢失：再投递也不多出一条消息。"),
        step("H09", "客户收到回复，继续沟通或反馈", "N3 → N2 / N1 → 浏览器", "正式 M07 与授权通知", "补事件 / 快照恢复、去重；评价回到反馈闭环。", "客户看到有署名的正式人工回复", "N3 收集评价；纠错原始证据不覆盖。", "客户离线时先保存；重新登录后可补查 M07。", link="closure", color="green"),
        step("H10", "分别处理工单结束和控制交还", "N7 / N3 / N5 各自领域", "明确的关闭、退出人工或售后办理动作", "每项独立授权与状态转换；未交还控制不自动续办旧草稿。", "工单关闭 ≠ AI 恢复 ≠ AS001 办结", "各领域保存自己的结束事实和审计。", "客服关闭 TK01，不代表退款已到账或自动创建新申请。", color="gold"),
    ], example="E4：HD01 → TK01 → ASSIGN01 → REPLY01 / EVT01 → M07，每个 ID 都对应不同责任和完成时点。")

    flow("closure", "12", "第 2 层 · 例 3：一次差评如何真正闭环", "只把经过归因、修复、独立回归和审批发布的改动计为改进；收到差评本身不是闭环完成。", [
        step("Q01", "收集原始反馈或人工纠错", "用户 → N3；客服纠错 → N7", "M02 / R01、评价理由、版本引用", "保存原始证据与本领域 Outbox；不让评价直接改知识答案。", "FB01：材料说明含糊；可追溯 P003 / KB003", "N3 评价；N7 纠错，各保留原文与合法引用。", "用户差评：“没有讲清楚要提供什么照片。”", phase="采集：消息 → 反馈 → 可追溯的修复项"),
        step("Q02", "可靠投递并归因到责任领域", "Outbox Relay → Redis → N8 → 责任领域", "反馈 / 错误事件、来源、event_id", "去重、审核；知识归 N6，路由 N4，业务 N5，人工 N7。", "本例建立知识修复项，关联 FB01 与证据", "责任领域 Inbox 与效果提交后才 ACK；跨域总工作项归属待 M13 ADR。", "物流数据错误应修 N5 数据链，不用改 Prompt 掩盖。", side=("重复 / 不可处理事件", "同 ID 幂等；未知 schema 隔离告警；超限重试进入人工处理。", None)),
        step("Q03", "审核修复建议，准备候选原文", "管理台 → N2 → N6", "经批准的修订内容、权限范围与责任人", "确认缺陷归因和修订依据；上传受控文件并检查类型 / 大小 / 内容安全。", "P004 候选原文；未安全通过不能标 READY", "MinIO 保存原文；N6 MySQL 保存状态 / 哈希 / Outbox。", "补清楚照片应覆盖哪里；不能凭差评杜撰商家规则。", side=("也可从上传进入", "日常知识新增直接从此处开始；不要求先产生差评。", None), phase="构建：原文候选 → 派生索引候选"),
        step("Q04", "处理跨存储中间状态", "N6 / 受托 N8 处理器", "上传对象、元数据、哈希与状态", "VALIDATING 通过后 READY；对象与元数据失配时补偿或隔离。", "可解析的授权原文；尚不可正式检索", "对象写入与 SQL 不是一个原子事务。", "对象上传成功但登记失败 → 隔离补偿，不直接发布。", side=("撤回 / 检查失败", "先禁止访问；清理 / 重建异步对账，缺失安全检查不算通过。", None)),
        step("Q05", "解析、切片、向量化、构建候选", "N6 处理器；N8 调度", "READY 原文、解析配置、目标知识版本", "清洗解析 → 分块 → Embedding → 候选索引；按哈希与版本去重。", "KB004 候选索引与来源块映射", "MinIO 原文；MySQL 元数据；Milvus 派生索引。", "用同一兼容向量配置建 KB004；线上仍读 KB003。"),
        step("Q06", "独立回归和质量门禁", "N6 / 相关领域测试与审核人", "候选版本、原 Bad Case、Golden Set、验收指标", "验证正确性、权限隔离、失败恢复、质量和性能；修复样本之外也回归。", "证据完整且门禁通过 → Q07；失败 → 修复候选", "保留评测配置、数据版本与结果；阈值未冻结不准发布。", "原问题回答清楚，同时确认未泄露另一个商家的政策。", side=("回归未通过", "回 Q03–Q05 修复；线上版本不变，不以“跑过一次”代替验收。", None), phase="发布门：独立回归 → 审批 → 激活", color="gold"),
        step("Q07", "审批并激活兼容版本组合", "授权发布人 → 各领域版本端口", "KB / 规则 / Router / Prompt 等兼容关系与审批", "索引完整后切换；缓存绑定版本；审计发布并可回退已验证组合。", "KB004 发布；本例 RULE003 不变且已证明兼容", "知识 / 规则 / 路由版本分别由其领域拥有，不跨表修改。", "政策有效时间按批准规则解释，不强行套最新政策到旧订单。", side=("发布失败 / 撤权", "保留或回退已验证版本；权限撤销优先于固定版本和缓存。", None), color="gold"),
        step("Q08", "新请求验证效果，归档关闭证据", "新请求 → N4 / N6；审核人 → 责任领域", "新 R09 + KB004；FB01 对应的修复与回归证据", "新请求读取已发布版本，独立核对改善；保留继续观察和回退依据。", "形成一次完整闭环；回图 06 A01", "反馈 → 修复 → 测试 → 审批 → 发布 → 新请求均可追溯。", "R09 给出清楚的照片说明；满足约定门禁后关闭修复项。", color="green"),
    ], example="E5：M02 差评 → FB01 → P004 候选 → KB004 回归 → 审批发布 → R09 验证。例子不表示这些环节已经运行。")

    flow("page", "13", "第 2 层 · 页面申请与聊天如何共用事实", "同一个 N5 预检和提交端口，两种入口。页面不经过 N4 意图识别，也不制造 conversation / Run。", [
        step("P01", "打开订单 / 售后页面", "浏览器 → N1 → N2 → N5", "登录身份、目标订单和页面查询参数", "入口认证后，由 N5 再校验归属并查询当前事实。", "授权订单 / 商品行 / 可申请范围", "读取 N5，既不调 KF，也不创建聊天记录。", "U01 打开 O1001，选 L1 ×1。", phase="页面入口：业务操作不是聊天消息"),
        step("P02", "填写申请并请求同一个 N5 预检", "浏览器 → N2 → N5 preflight", "动作、数量、理由、READY 材料引用", "重验权限、状态和规则，绑定载荷哈希及展示摘要。", "PF02、有效期、事实 / 规则版本和申请摘要", "N5 拥有 preflight；页面不创建 N4 Workflow。", "DEMO 摘要：申请退货，L1 ×1，申请金额 19900 分 CNY。"),
        step("P03", "用户核对并明确确认", "浏览器 / N5", "PF02 和预检给出的原摘要", "用与提交载荷相同的信息让用户确认；不能默认勾选或用阅读代替确认。", "当前有效预检下的明确提交动作", "N5 保存服务端确认 / 提交证据；按钮禁用不能代替幂等。", "改数量、改操作、过期或事实变化 → 新预检和新确认。", side=("变更 / 取消", "未提交可取消；载荷变化回 P02，不复用旧预检。", None), color="gold"),
        step("P04", "调用统一受控提交端口", "浏览器 → N2 → N5 submit", "PF02、原载荷、稳定幂等标识", "同预检只映射一个 command_id；N5 再核验所有领域约束。", "CMD02；真实命令执行 / 受理状态", "N5 保存命令与业务事实；channel=PAGE 仅审计。", "CHAT 与 PAGE 不构成两份权限，也不能绕过可申请数量。", side=("另一入口重复申请", "不同预检 / 不同键仍受 N5 剩余数量和业务语义约束；不能超额创建。", None)),
        step("P05", "结果未知时查原命令", "页面 → N2 → N5 query", "CMD02 / 原幂等关联", "超时或刷新查同一个命令；收到 UNKNOWN 不当成失败后另建。", "确定结果，或仍待查询 / 对账的状态", "N5 是权威；本地缓存没有结果不代表提交失败。", "200 查询响应只表示查到当前状态，不承诺申请成功。", side=("页面失联", "重新认证后恢复查询；没有必要创建一段假聊天来恢复。", None), phase="恢复与一致性：事实只认 N5"),
        step("P06", "页面展示真实申请，聊天可查询", "N5 → 页面；后续聊天经 N4 → N5", "实际 after_sale_id、命令与申请状态", "展示申请单；以后聊天查询也读取同一 N5 事实。", "同一申请跨入口可见，权限每次校验", "仅聊天查询的答复才由 N3 保存正式消息。", "若 AS001 已占用 L1 全部数量，新申请被限制并提示已有单。", color="green"),
    ], example="E6：独立页面成功路径可使用 PF02/CMD02；若例 1 的 AS001 已占满数量，本页不能再成功创建第二单。")


def esc(s):
    return html.escape(str(s), quote=True)


def wrap(s, units):
    """Wrap CJK by approximate display width; browser QA verifies actual glyph boxes."""
    result, line, used = [], "", 0
    for ch in re.findall(r"[A-Za-z0-9_./-]+|.", s):
        cost = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1.35 for c in ch)
        keep_punctuation = units >= 50 and ch in "，。；：！？、）】”"
        if used + cost > units and line and not keep_punctuation:
            result.append(line.rstrip())
            line, used = "", 0
        if not line and ch.isspace():
            continue
        line += ch
        used += cost
    if line:
        result.append(line)
    return result


def text(x, y, value, size=20, fill="#edf4fe", weight=400):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}">{esc(value)}</text>'


def render(f):
    nodes, edges, labels = [], [], []
    y = 158
    positions = []
    for i, n in enumerate(f["nodes"]):
        if n["phase"]:
            if i:
                y += 20
            labels.append(f'<rect x="42" y="{y}" width="1116" height="43" rx="8" fill="#20324a"/>')
            labels.append(text(60, y + 29, n["phase"], 21, "#c3d5eb", 700))
            y += 65
        rows = [("输入", n["incoming"], "#d7e8fa"), ("处理", n["action"], "#edf4fe"),
                ("输出", n["outgoing"], C["green"]), ("落点", n["persist"], "#b8c8dd"),
                ("示例", n["example"], C["gold"])]
        lines = [(label, wrap(value, 58), color) for label, value, color in rows]
        height = 95 + sum(len(parts) * 28 + 8 for _, parts, _ in lines) + (35 if n["link"] else 0)
        x, width, color = 64, 728, C[n["color"]]
        body = [f'<g id="{esc(n["key"])}" class="node" data-box="{x},{y},{width},{height}">',
                f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="#122137" stroke="{color}" stroke-width="2"/>',
                f'<rect x="{x}" y="{y+14}" width="5" height="38" rx="2" fill="{color}"/>',
                text(x+19, y+35, n["key"] + "  " + n["title"], 22, color, 700),
                text(x+19, y+66, "责任节点：" + n["owner"], 18, "#b8c8dd")]
        yy = y + 102
        for label, parts, col in lines:
            body.append(text(x+19, yy, label, 19, col, 700))
            for line in parts:
                body.append(text(x+77, yy, line, 20, col))
                yy += 28
            yy += 8
        if n["link"]:
            target = next(t for t in FLOWS if t["key"] == n["link"])
            body += [f'<a href="V1分层流程与示例.html#{esc(n["link"])}" data-open="{esc(n["link"])}">',
                     text(x+19, yy, "展开图 " + target["number"] + " → " + target["title"].split(" · ")[-1], 18, C["blue"], 700), "</a>"]
        body.append("</g>")
        nodes.append("".join(body))
        if n["side"]:
            title, detail, link = n["side"]
            sidex, sidey, sw = 866, y + 24, 294
            titlelines, detailines = wrap(title, 26), wrap(detail, 27)
            sh = 38 + len(titlelines)*26 + len(detailines)*27 + (34 if link else 12)
            sidebody = [f'<g class="side-node" data-box="{sidex},{sidey},{sw},{sh}">',
                        f'<rect x="{sidex}" y="{sidey}" width="{sw}" height="{sh}" rx="10" fill="#2b2330" stroke="{C["gold"]}" stroke-dasharray="5 4"/>']
            sy = sidey + 29
            for line in titlelines:
                sidebody.append(text(sidex+16, sy, line, 20, C["gold"], 700)); sy += 26
            sy += 10
            for line in detailines:
                sidebody.append(text(sidex+16, sy, line, 19, "#f3dee0")); sy += 27
            if link:
                number = next(t["number"] for t in FLOWS if t["key"] == link)
                sidebody.extend([f'<a href="V1分层流程与示例.html#{esc(link)}" data-open="{esc(link)}">', text(sidex+16, sy+7, f"查看图 {number} →", 18, C["blue"], 700), "</a>"])
            sidebody.append("</g>")
            nodes.append("".join(sidebody))
            edges.append(f'<path class="flow-edge side-edge" d="M792,{sidey+35} H856"/>')
        positions.append((y, height, n))
        y += height + 78
    for (start, height, node), (end, _, _) in zip(positions, positions[1:]):
        edges.append(f'<path class="flow-edge" d="M428,{start+height} V{end-10}"/>')
        labels.append(text(449, start+height+32, node["onward"], 17, "#b4c9df"))
    height = y + 28
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" id="diagram-{f['key']}" width="{W}" height="{height}" viewBox="0 0 {W} {height}" role="img" aria-labelledby="title-{f['key']}">
<title id="title-{f['key']}">{esc(f['title'])}</title>
<defs><marker id="arrow-{f['key']}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#65cbe0"/></marker></defs>
<style>text{{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif}}#diagram-{f['key']} .flow-edge{{fill:none;stroke:#65cbe0;stroke-width:2;marker-end:url(#arrow-{f['key']})}}#diagram-{f['key']} .side-edge{{stroke-dasharray:6 4}}a:hover text{{text-decoration:underline}}</style>
<rect width="1200" height="{height}" fill="#0c1626"/>
{text(42,49, f['title'],30,C['blue'],700)}
{text(42,86, '纵向实线＝选中路径的先后顺序；侧向虚线＝条件出口 / 例外；跨图入口标注目的地。',20,'#b8c8dd')}
{text(42,119, 'V1 目标设计 · 标准 1.1 · 示例均为虚构 DEMO · 不代表运行验收通过',19,C['gold'])}
{''.join(edges)}{''.join(labels)}{''.join(nodes)}
{text(42,height-25,'N1–N9 是责任节点，不是执行顺序；示例字段帮助审查，不替代后续正式 API / 数据合同。',18,'#b8c8dd')}
</svg>'''
    stem = f'{f["number"]}_{f["key"]}_分层流程'
    (OUT / f"{stem}.svg").write_text(svg, encoding="utf-8")
    f.update(stem=stem, svg=svg, height=height)


def build():
    content()
    for f in FLOWS:
        render(f)
    nav = []
    for f in FLOWS:
        if f['key'] == 'overview':
            nav.append('<small>第一层 · 全程主干</small>')
        elif f['key'] == 'routing':
            nav.append('<small>第二层 · 分支与后续</small>')
        label = f['title'].split(' · ')[-1]
        if f['key'] == 'kf':
            label = '↳ 第三层：KF 内部'
        inset = ' style="margin-left:16px;border-left:3px solid #c1adff"' if f['key'] == 'kf' else ''
        nav.append(f'<button data-open="{f["key"]}"{inset}><span>{f["number"]}</span>{esc(label)}</button>')
    nav = ''.join(nav)
    panels = []
    for f in FLOWS:
        options = ''.join(f'<option value="{esc(n["key"])}">{esc(n["key"] + " · " + n["title"])}</option>' for n in f['nodes'])
        panels.append(f'''<section data-panel="{f['key']}" hidden aria-labelledby="heading-{f['key']}">
<p class="crumb">{esc(f['parents'])} / 图 {f['number']}</p><h2 id="heading-{f['key']}">{esc(f['title'])}</h2>
<p>{esc(f['intro'])}</p><p class="example">{esc(f['example'])}</p>
<div class="toolbar"><label>定位节点 <select aria-label="定位节点">{options}</select></label><button class="jump">定位</button><button class="fit">适应宽度</button><button class="actual">原始尺寸</button><a href="{f['stem']}.svg" download>SVG</a><a href="{f['stem']}.png" download>高清 PNG</a></div>
<div class="canvas">{f['svg']}</div></section>''')
    template = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V1 分层流程与逐节点示例</title><style>
*{box-sizing:border-box}body{margin:0;background:#0c1626;color:#eaf3ff;font:16px/1.7 "Microsoft YaHei",sans-serif}header{padding:24px 30px 20px;background:#132238;border-bottom:1px solid #36506b}h1{font-size:27px;margin:0 0 8px}h2{font-size:25px;margin:0 0 10px}p{margin:7px 0;color:#c1d0e2}header p{max-width:1150px}.badge{color:#f1be63}.layout{display:grid;grid-template-columns:236px minmax(0,1fr)}aside{position:sticky;top:0;height:100vh;overflow:auto;padding:20px 14px;background:#111f33;border-right:1px solid #30425d}aside p{font-size:14px;padding:0 10px}nav{display:grid;gap:9px}button,a,select{font:inherit;border:1px solid #3e5a77;border-radius:7px;background:#192c44;color:#96e1ef;padding:7px 10px;text-decoration:none;cursor:pointer}button:hover,a:hover{border-color:#f1be63}nav button{text-align:left;font-size:14px;line-height:1.5}nav button span{display:inline-block;width:28px;color:#7d9ab9}nav button[aria-current="page"]{background:#214462;border-color:#77d3e5;color:#fff}main{min-width:0;padding:22px}.crumb{color:#91accb;font-size:14px}.example{background:#2b2931;color:#f6d895;border-left:4px solid #f1be63;padding:10px 14px}.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:16px 0}.toolbar label{font-size:14px}.toolbar button,.toolbar a,.toolbar select{font-size:14px}.toolbar select{max-width:290px}.canvas{overflow:auto;border:1px solid #314960;border-radius:10px}.canvas svg{display:block;height:auto;width:100%;min-width:880px}section[hidden]{display:none}footer{font-size:14px;margin:25px 0;padding:20px;border-top:1px solid #334960}details{margin:12px 0;background:#122137;border:1px solid #36506b;border-radius:8px;padding:10px 14px}summary{cursor:pointer;color:#94dce9;font-weight:bold}table{border-collapse:collapse;width:100%;font-size:14px;margin:12px 0}td,th{padding:9px;border:1px solid #344d68;text-align:left;vertical-align:top}th{background:#20334b}code{color:#9bddc2}ul{padding-left:23px}@media(max-width:800px){.layout{display:block}aside{position:static;height:auto}nav{grid-template-columns:repeat(2,minmax(0,1fr))}main{padding:12px}header{padding:18px}h1{font-size:23px}}@media print{header,aside,.toolbar,footer{display:none}.layout{display:block}main{padding:0}.canvas{overflow:visible;border:0}.canvas svg{min-width:0;width:100%!important}}
nav small{grid-column:1/-1;color:#b7c9df}
</style></head><body><header><h1>V1 分层流程与逐节点示例</h1><p>第 1 层看全程 → 第 2 层只展开选中的业务 → 第 3 层检查 KF 内部与每个节点的数据。每张图都沿一条竖直主干往下读，条件出口单独放右侧。</p><p class="badge">这是目标设计与演示数据，不是已运行的平台。M00.1–M00.4 已完成；93 条业务用例仍 NOT_RUN；不启动 M01.1。</p></header>
<div class="layout"><aside><p>阅读树 / 先总后分</p><nav aria-label="分层流程导航">__NAV__</nav><p>总图 A01–A09 为全程。子图中的数字仅代表该子图步骤；不是新的服务编号。</p><p>每个框固定五项：输入 → 处理 → 输出 → 落点 → 示例。</p></aside><main>
<details><summary>先理解数据归谁、为什么不是所有箭头都叫“成功”</summary>
<table><tr><th>责任节点</th><th>唯一负责的事实</th><th>不应混淆</th></tr><tr><td>N1 / N2</td><td>统一入口 / 身份、租户、角色与安全约束</td><td>入口授权不代替 N5 业务归属与资格校验</td></tr><tr><td>N3</td><td>正式会话、控制模式、消息、评价、通知</td><td>不从 KF 诊断历史恢复正式消息</td></tr><tr><td>N4</td><td>Run、确定性路由、Workflow、确认与命令意图</td><td>不拥有订单事实，不替模型放开业务写权限</td></tr><tr><td>N5</td><td>订单 / 包裹 / 商品 / 售后 / 发票事实、批准规则、预检与命令</td><td>资格成立、申请受理、审批通过、退款到账是不同事实</td></tr><tr><td>N6</td><td>知识原文与元数据、索引版本、KF 检索与生成</td><td>保留核心；隔离诊断历史；不能审批订单或执行资金</td></tr><tr><td>N7 / N8 / N9</td><td>工单与人工记录 / 任务执行与投递 / 可观测性</td><td>N8 通过所属领域端口做事；N9 日志不能代替领域事务审计</td></tr></table>
<p>MySQL 是各领域的权威数据；MinIO 存原文 / 附件；Milvus 存可重建索引；Redis / Streams 存缓存和投递状态，不能是唯一事实。逻辑边界不要求 V1 将所有模块拆成独立进程。</p></details>
__PANELS__
<details><summary>六个例外，快速检查有没有走错路</summary><table><tr><th>情况</th><th>应走的路</th><th>不允许发生</th></tr><tr><td>订单不是当前用户的</td><td>A02 / T01 拒绝，必要时隐藏资源存在性</td><td>把他人订单送给 RAG 后才过滤</td></tr><tr><td>两个订单，不知道退哪个</td><td>B04 澄清 → 新一轮选择</td><td>模型自行选一个并提交</td></tr><tr><td>证据不足或适用政策冲突</td><td>K5 → K7 无法确认；N4 选择澄清 / 人工</td><td>用模型常识编政策或判资格</td></tr><tr><td>重复点击、超时、刷新</td><td>T09 / T10 / P05 查同一预检与命令</td><td>换新幂等键重新做未知写操作</td></tr><tr><td>人工已接管，旧 AI 晚到</td><td>H01 / F02 / F04 控制守卫抑制旧答案</td><td>AI 继续公开回复或续办旧草稿</td></tr><tr><td>修复发布失败或索引不兼容</td><td>Q06 / Q07 留候选或回退已验证版本</td><td>候选库未经审批接正式查询</td></tr></table></details>
<footer>依据：<a href="../../implementation-standards/v1/README.md">四份实施标准 1.1</a>、<a href="../module-boundaries.md">模块边界</a>、KF 只读源码。<a href="V1平台端到端详细流程.html">图 05 密集综合视图</a>保留供对照，推荐以本分层页阅读。<a href="V1分层流程_示例走读.md">示例走读说明</a>。本次只修改文档展示，不改参考项目、核心 Pipeline 或技术选型。</footer>
</main></div><script>
function openFlow(key, update=true){const panel=document.querySelector('[data-panel="'+key+'"]');if(!panel)return false;document.querySelectorAll('[data-panel]').forEach(p=>p.hidden=p!==panel);document.querySelectorAll('nav [data-open]').forEach(b=>b.setAttribute('aria-current',b.dataset.open===key?'page':'false'));if(update)history.replaceState(null,'','#'+key);window.scrollTo({top:0,behavior:'instant'});return true;}
document.querySelectorAll('[data-open]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault();openFlow(el.dataset.open);}));
document.querySelectorAll('[data-panel]').forEach(p=>{p.querySelector('.jump').onclick=()=>{const target=p.querySelector('[id="'+p.querySelector('select').value+'"]');target.scrollIntoView({behavior:'instant',block:'start'});};p.querySelector('.actual').onclick=()=>p.querySelector('svg').style.width='1200px';p.querySelector('.fit').onclick=()=>p.querySelector('svg').style.width='100%';});
window.addEventListener('hashchange',()=>openFlow(location.hash.slice(1),false));if(!openFlow(location.hash.slice(1),false))openFlow('overview',false);
</script></body></html>'''
    (OUT / "V1分层流程与示例.html").write_text(template.replace("__NAV__", nav).replace("__PANELS__", "".join(panels)), encoding="utf-8")
    manifest = [dict(key=f["key"], stem=f["stem"], width=W, height=f["height"], nodes=[n["key"] for n in f["nodes"]]) for f in FLOWS]
    (OUT / "source" / "layered-flow-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(FLOWS)} diagrams with {sum(len(f['nodes']) for f in FLOWS)} main nodes.")


if __name__ == "__main__":
    build()
