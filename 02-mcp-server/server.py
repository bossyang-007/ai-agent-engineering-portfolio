"""
项目 02：MCP Server 实现（质检数据查询工具集）
设计目标：体现 MCP 的协议层设计，而不只停留在"调用现成 Server"。

为什么这个场景有意义：
- 我把自己的数据能力（投诉文本分类、分类别治理指标）封装成 MCP Server，
  任何支持 MCP 的 Host（如 Claude Desktop 或 IDE 扩展）都能直接调用；
- 演示了 MCP 的三类原语：Tools（可调用操作）、Resources（只读数据）、Prompts（提示词模板）；
- 演示了工具注解（annotations）标注风险等级 —— 客户端据此决定要不要弹人工确认。

⚠️ 技术栈版本（技术要点）：本代码基于 **MCP Python SDK 2.x**。
   2.0 的重大变更：**FastMCP 更名为 MCPServer**（from mcp.server.mcpserver import MCPServer），
   装饰器式 API 取代了 v1 的 @server.list_tools() / @server.call_tool() 写法。
   对应 2026-07-28 规范：协议层无状态化、server/discover 能力发现、Tools 移入扩展、
   Tool Annotations 风险语义、企业托管授权（EMA）。
   → 迁移说明："我从 v1 的低层 Server API 迁到 v2 的 MCPServer 高层 API，
      迁移过程中最大的体会是协议在往'开箱即用'的方向收敛，但企业级要求的能力
      （无状态、鉴权、审计）反而更显式了。"

运行：
    python server.py                # stdio 传输（本地客户端用）
    python server.py --http         # Streamable HTTP（远程部署用）
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

# ---------------------------------------------------------------------------
# 模拟业务数据（生产环境里这里接数据库 / 数仓 / API）
# ---------------------------------------------------------------------------

CATEGORY_STATS = {
    "网络": {"count": 41207, "avg_handle_hours": 18.3, "first_contact_resolution": 0.91},
    "资费": {"count": 23815, "avg_handle_hours": 26.7, "first_contact_resolution": 0.78},
    "终端": {"count": 15432, "avg_handle_hours": 15.1, "first_contact_resolution": 0.85},
    "服务": {"count": 33190, "avg_handle_hours": 41.2, "first_contact_resolution": 0.62},
    "其他": {"count": 8926, "avg_handle_hours": 33.4, "first_contact_resolution": 0.71},
}

SAMPLE_CASES = [
    {"id": "QC-20260901-0142", "text": "手机经常掉线，客服说让我重启路由器", "label": "网络", "confidence": 0.93},
    {"id": "QC-20260903-0287", "text": "上个月套餐自动续费没告诉我，多扣了 50", "label": "资费", "confidence": 0.97},
    {"id": "QC-20260905-0331", "text": "换了新手机后旧手机上号了，营业厅不给销号", "label": "终端", "confidence": 0.88},
]

CATEGORY_DEFINITIONS = {
    "网络": "断网、掉线、信号弱、无法上网、网速慢等连通性问题",
    "资费": "扣费异常、套餐争议、账单疑问、流量超额等费用问题",
    "终端": "手机故障、终端损坏、号码与设备相关的问题",
    "服务": "客服态度、处理时效、推诿扯皮等服务质量问题",
    "其他": "以上四类未覆盖的问题",
}

server = MCPServer(
    name="qc-data-server",
    version="0.1.0",
    instructions=(
        "质检数据查询工具集。用于查询各类用户投诉的量级、处理时长、一次解决率，"
        "以及检索历史 bad case。所有工具均为只读操作，不修改任何业务数据。"
    ),
)


# ---------------------------------------------------------------------------
# Tools：模型可调用的操作
# ---------------------------------------------------------------------------


@server.tool(
    name="query_category_stats",
    title="查询分类别治理指标",
    description=(
        "查询各类用户投诉的量级、平均处理时长与一次解决率。"
        "当需要评估某类问题的业务影响面、或做资源优先级排序时使用。"
        "参数 category 可传'全部'返回所有类别。"
    ),
    annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
)
def query_category_stats(category: str) -> str:
    """查询分类别指标。参数错误时返回可读的业务错误，而非抛异常。"""
    if category == "全部":
        return json.dumps(CATEGORY_STATS, ensure_ascii=False, indent=2)
    if category not in CATEGORY_STATS:
        return f"错误：未知类别 '{category}'，可选值：{'/'.join(CATEGORY_STATS)}"
    return json.dumps({category: CATEGORY_STATS[category]}, ensure_ascii=False, indent=2)


@server.tool(
    name="search_bad_cases",
    title="检索历史 bad case",
    description=(
        "按问题类别检索历史 bad case（模型误判样本）。"
        "当需要做错误归因、扩充标注数据、或设计 few-shot 示例时使用。"
    ),
    annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
)
def search_bad_cases(category: str, limit: int = 5) -> str:
    """检索 bad case 样本。limit 有上下界保护，防止一次拉爆上下文。"""
    limit = max(1, min(int(limit), 20))
    hits = [c for c in SAMPLE_CASES if c["label"] == category][:limit]
    if not hits:
        hits = SAMPLE_CASES[:limit]
    return json.dumps(hits, ensure_ascii=False, indent=2)


@server.tool(
    name="compute_impact_score",
    title="计算治理优先级得分",
    description=(
        "根据量级、处理时长与一次解决率计算问题治理的优先级得分。"
        "当需要在多个问题类别之间做投入产出排序时使用。"
    ),
    annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
)
def compute_impact_score(category: str) -> str:
    """计算治理优先级。公式对调用方透明，便于核对与复算。"""
    if category not in CATEGORY_STATS:
        return f"错误：未知类别 '{category}'"
    s = CATEGORY_STATS[category]
    score = s["count"] / 1000 + s["avg_handle_hours"] + (1 - s["first_contact_resolution"]) * 50
    return json.dumps(
        {
            "category": category,
            "impact_score": round(score, 2),
            "formula": "count/1000 + avg_handle_hours + (1-fcr)*50",
            "inputs": s,
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Resources：只读数据（由应用控制何时读取）
# ---------------------------------------------------------------------------


@server.resource("qc://schema/categories", name="投诉类别体系", mime_type="application/json")
def categories_schema() -> str:
    """投诉分类的标准体系与各类定义，用于保证标签口径一致。"""
    return json.dumps(CATEGORY_DEFINITIONS, ensure_ascii=False, indent=2)


@server.resource("qc://dataset/sample", name="样例标注数据", mime_type="application/json")
def sample_dataset() -> str:
    """少量已标注样本，供 few-shot 示例与评测集构建。"""
    return json.dumps(SAMPLE_CASES, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Prompts：预置提示词模板（由用户控制）
# ---------------------------------------------------------------------------


@server.prompt(
    name="bad_case_归因",
    title="bad case 归因分析模板",
    description="对一批 bad case 做系统性归因，输出根因分布与改进建议",
)
def bad_case_attribution_prompt(category: str, sample: str = "（未提供）") -> str:
    """生成归因分析提示词。

    设计说明：Prompt 由**用户**主动触发（不是模型自动调用），
    所以模板里可以放人写的判断标准 —— 这是它和 Tool 的根本区别。
    """
    return f"""你是投诉治理的质量分析专家。请对「{category}」类别的以下样本做归因分析：

{sample}

分析要求：
1. 先给每条样本打上「口径混淆 / 边界误判 / 特征不足 / 标签噪声」四类根因之一；
2. 统计各根因占比，指出主要矛盾；
3. 给出可执行改进（标注规范修订 / 特征补充 / 样本扩充 / 规则前置）；
4. 输出必须区分「已观察到的事实」与「推测」，不得越过证据下结论。
"""


# ---------------------------------------------------------------------------
# 传输层
# ---------------------------------------------------------------------------


def run_stdio() -> None:
    """stdio 传输：本地进程内通信（Claude Desktop / IDE 插件常用）。

    设计说明：stdio 适合本地工具（IDE、桌面端插件），
    优点是无需网络、无鉴权面；缺点是无法多租户、无法横向扩展。
    """
    server.run(transport="stdio")


def run_http() -> None:
    """Streamable HTTP 传输：远程部署。

    设计说明（对应 2026-07-28 规范的无状态化）：
    协议层移除 session 后，远程 Server 可以直接挂在普通轮询负载均衡器后面，
    **不再需要 sticky session 与共享 session 存储** ——
    这是 MCP 从"个人玩具"走向"企业生产"的运维前提。
    """
    port = int(os.environ.get("PORT", "8931"))
    server.run(transport="streamable-http", host="127.0.0.1", port=port)


if __name__ == "__main__":
    if "--http" in sys.argv:
        run_http()
    else:
        run_stdio()
