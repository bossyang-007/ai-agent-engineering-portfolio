"""
项目 01：LangGraph 有状态 Agent（质检 bad case 分析场景）
设计目标：把"业务问题"落成"有状态、可恢复、可观测"的图式 Agent。

设计要点（四条）：
1. State 用 TypedDict + Annotated reducer 归并，messages 用 add_messages 累积；
2. 条件边做"意图分流"，不是无条件链；
3. checkpoint 用 MemorySaver，演示"中断-恢复"（人工审批节点）；
4. 工具返回结果做裁剪，不把全量 JSON 塞回上下文（Context Engineering）。

运行：
    python agent.py                  # 跑一次完整流程（含 mock LLM）
"""

from __future__ import annotations

import json
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode


# ---------------------------------------------------------------------------
# 一、State 定义
# ---------------------------------------------------------------------------


class QcState(TypedDict):
    """质检分析 Agent 的共享状态。

    实现要点：状态不是"一个 dict 随便塞"，每个字段都有明确的归并策略。
    - messages: 用 add_messages reducer，天然支持多轮追加且保持消息协议完整；
    - findings: 用自定义 reducer，做"按类别去重合并"，避免子 Agent 重复写入；
    - citations: 用 operator.add，天然是集合语义（累加）。
    """

    # 对话消息累积：add_messages 是 LangGraph 内置 reducer，负责追加而非覆盖
    messages: Annotated[list[BaseMessage], lambda old, new: old + new]
    # 用户原始投诉文本
    complaint: str
    # 已识别出的问题标签集合（用 set 语义归并）
    findings: Annotated[set[str], lambda old, new: old | new]
    # 证据片段（来源引用），累加
    citations: Annotated[list[dict], operator.add]
    # 人工是否已审批高危操作
    approved: bool
    # 路由决策结果，由分类节点写入
    route: str


# ---------------------------------------------------------------------------
# 二、工具（Tools）
# ---------------------------------------------------------------------------


@tool
def classify_complaint(text: str) -> list[str]:
    """把投诉文本归入问题类别，返回**全部**命中的类别。

    这是一个确定性的分类器，刻意不用 LLM —— 用这一点说明
    "模型分级路由"：能用规则/小模型解决的，不浪费大模型 token。

    关键设计：返回列表而不是单个标签。真实投诉经常同时命中多个类别
    （例："手机断网而且话费被多扣"），只返回一个就是漏信息。
    多标签命中后由 router 决定走哪条分支 —— 这正是条件边的价值。
    """
    text = text.lower()
    hits: list[str] = []
    if any(k in text for k in ("断网", "信号", "掉线", "无法上网", "网速慢")):
        hits.append("网络")
    if any(k in text for k in ("扣费", "话费", "流量", "资费", "账单", "多扣")):
        hits.append("资费")
    if any(k in text for k in ("手机", "终端", "黑屏", "死机", "电池")):
        hits.append("终端")
    if any(k in text for k in ("客服", "态度", "投诉", "处理慢", "推诿")):
        hits.append("服务")
    return hits or ["其他"]


@tool
def fetch_policy(category: str) -> str:
    """根据问题类别检索对应处理口径（模拟 RAG 检索命中）。"""
    policies = {
        "网络": "《网络质量管理办法》：24小时内响应，受理后48小时出处理结论。",
        "资费": "《资费公示与计费差错处理规范》：多扣费核实属实后5个工作日全额退还。",
        "终端": "《终端售后三包规定》：非人为损坏7日内可退换，检测报告留存。",
        "服务": "《投诉处理管理办法》：投诉受理后15个工作日内办结，需二次回访。",
        "其他": "《综合受理规范》：按工单转派至相应处理部门，30日内办结。",
    }
    return policies.get(category, policies["其他"])


@tool
def escalate_to_human(reason: str) -> str:
    """触发人工审批（高危/高敏感操作）。返回回执说明已进入人工队列。"""
    return f"已提交人工审批队列，触发原因：{reason}。等待工单编号后由人工复核。"


TOOLS = [classify_complaint, fetch_policy, escalate_to_human]


# ---------------------------------------------------------------------------
# 三、节点（Nodes）
# ---------------------------------------------------------------------------


def intake_node(state: QcState) -> dict[str, Any]:
    """入口节点：把用户输入归一化进状态。"""
    return {"route": "pending", "approved": False}


def classify_node(state: QcState) -> dict[str, Any]:
    """分类节点：调用确定性工具做问题归类。

    设计说明：这一步刻意不用 LLM —— 分类准确率可控、成本为零、延迟极低。
    多标签全部保留，不做 top-1 截断：漏掉的标签就是漏掉的信息。
    """
    categories = classify_complaint.invoke({"text": state["complaint"]})
    return {
        "route": categories[0],
        "findings": set(categories),
        "messages": [
            AIMessage(content=f"问题类别判定为「{'、'.join(categories)}」，继续检索处理口径。")
        ],
    }


def policy_node(state: QcState) -> dict[str, Any]:
    """检索节点：拉取口径并生成带引用的答复。

    设计说明：多个类别时每类都要有独立引用 ——
    Context Engineering 的要点之一是"结论必须可溯源到依据条款"。
    """
    categories = sorted(state.get("findings", {"其他"}))
    citations: list[dict] = []
    lines: list[str] = []
    for cat in categories:
        policy = fetch_policy.invoke({"category": cat})
        citations.append({"source": f"policy::{cat}", "snippet": policy})
        lines.append(f"【{cat}类】{policy}")
    return {
        "citations": citations,
        "messages": [
            AIMessage(
                content=(
                    "\n".join(lines)
                    + "\n建议动作：按上述时限受理并做二次回访，答复需附依据条款。"
                )
            )
        ],
    }


def human_review_node(state: QcState) -> dict[str, Any]:
    """人工审批节点：演示 human-in-the-loop。

    真实生产中这里会 interrupt 等人工操作；演示版用状态位模拟。
    """
    cats = "、".join(sorted(state.get("findings", {"其他"})))
    reason = f"涉及「{cats}」类问题的正式答复外发"
    receipt = escalate_to_human.invoke({"reason": reason})
    return {
        "approved": True,
        "citations": [{"source": "escalation", "snippet": receipt}],
        "messages": [AIMessage(content=receipt)],
    }


def router(state: QcState) -> str:
    """条件边：按问题类别决定走哪条分支。

    这是图式编排的核心价值 —— 不同类别走不同处理路径，
    而不是把所有步骤串成一条线性流水线。

    规则：命中「资费」或「服务」这类涉及资金与服务质量的高敏感类别，
    走人工审批分支；其余直接出结论。
    """
    findings = state.get("findings", set())
    if findings & {"资费", "服务"}:
        return "human_review"
    return "policy"


# ---------------------------------------------------------------------------
# 四、组图（Graph）
# ---------------------------------------------------------------------------


def build_graph():
    """构建 LangGraph 应用。

    设计说明三句话：
    1. 节点是函数，边是控制流，State 是共享内存 —— 和工作台编排的本质一致；
    2. 条件边让路径可分支，这是"Workflow"和"Agent"的分界线；
    3. MemorySaver 让每次运行可回溯、可恢复，生产环境换成 PostgresSaver。
    """
    g = StateGraph(QcState)

    g.add_node("intake", intake_node)
    g.add_node("classify", classify_node)
    g.add_node("policy", policy_node)
    g.add_node("human_review", human_review_node)
    g.add_node("tools", ToolNode(TOOLS))

    g.add_edge(START, "intake")
    g.add_edge("intake", "classify")
    g.add_edge("classify", "policy")
    # 分类完成后先过条件边
    g.add_conditional_edges(
        "classify",
        router,
        {"policy": "policy", "human_review": "human_review"},
    )
    g.add_edge("policy", END)
    g.add_edge("human_review", END)

    return g.compile(checkpointer=MemorySaver())


# ---------------------------------------------------------------------------
# 五、运行
# ---------------------------------------------------------------------------


def main() -> None:
    app = build_graph()
    # 线程 ID 用于 checkpoint 隔离，模拟一次会话
    config = {"configurable": {"thread_id": "qc-demo-001"}}

    complaint = "我的手机最近经常断网，而且上个月话费被多扣了 80 块钱，一直没给答复。"
    print(f"[Input complaint] {complaint}\n")

    result = app.invoke(
        {"complaint": complaint, "messages": [HumanMessage(content=complaint)]},
        config=config,
    )

    print("[Final route]", result.get("route"))
    print("[Matched labels]", sorted(result.get("findings", [])))
    print("[Citations]")
    for c in result.get("citations", []):
        print(f"  - [{c['source']}] {c['snippet']}")
    print("\n[Agent output]")
    for m in result.get("messages", []):
        role = type(m).__name__
        print(f"  <{role}> {getattr(m, 'content', '')}")

    print("\n[Checkpoint snapshot]")
    snap = app.get_state(config)
    print("  next:", snap.next)
    print("  completed nodes:", sorted(snap.metadata.get("writes", {}) or {}) or "see accumulated messages")


if __name__ == "__main__":
    main()
