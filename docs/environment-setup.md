# 环境与运行说明

## 一、依赖环境（已验证可用）

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.13.14 | 托管运行时 |
| 虚拟环境 | `C:\Users\HUAMEI\.workbuddy\binaries\python\envs\default` | 隔离环境，不污染系统 Python |
| langgraph | 1.2.17 | 图式 Agent 编排 |
| langchain-core | 1.7.0 | 消息协议、工具基类 |
| langgraph-checkpoint | 4.3.0 | checkpoint 持久化（生产换 Postgres） |
| mcp | 2.3.0 | **MCP 2.x**：FastMCP 已更名 MCPServer |
| mcp-types | 2.3.0 | 2.x 起独立成包 |
| pydantic / pydantic-core | 2.14.1 / 2.50.1 | 数据模型校验 |

**已验证可运行**（2026-10-24 实测）：
- 作品 01 输出正确：多标签识别（网络/资费/终端）、条件边走人工审批分支、3 条引用齐全
- 作品 02 输出正确：3 工具（annotations 生效）、2 资源、1 提示词；错误路径返回可读文案而非抛异常

**安装踩坑记录**：

1. **pip 对清华源返回 403**——`pip` 的 User-Agent 被清华 PyPI 镜像拦截，但 `curl` / `urllib` 正常。
   表现极具迷惑性：`pip install` 报 "Could not find a version ... (from versions: none)"，看起来像包不存在，实际是 403。
   定位方法：`pip install -vvv` 看 "Getting page ... 403 Forbidden"。
2. **pypi.org 直连时连接被重置**（ConnectionResetError 10054），需靠重试与指数退避。
3. **纯 `py3-none-any` 优先策略会装错平台的二进制包**——pydantic-core 会下到 macOS 或 win32 的 wheel，
   报 "is not a supported wheel on this platform"。必须按 `cp313-cp313-win_amd64` 精确匹配。
4. **稳定 ABI 标签要单独放行**——cryptography 的 wheel 名是 `cp39-abi3-win_amd64`，
   用 `cp313-cp313` 精确匹配会漏掉，必须放宽到 `-abi3-` 规则。
5. **纯 Python wheel 的标签有两种写法**——`xxx-py3-none-any.whl` 和 `xxx-py2.py3-none-any.whl`，
   只匹配前一种会漏掉 requests-toolbelt。
6. **最终解法**：用 PyPI JSON API 自行解析版本与文件列表 → 并行下载 → `pip install --no-deps --no-index` 本地安装，
   脚本保存在 `_fetch_pkgs.py`（环境目录下）。


## 二、运行方式

### 作品 01：LangGraph Agent

```bash
cd 01-langgraph-agent
python agent.py
```

预期输出：路由判断、命中标签、带来源的引用、Agent 输出、checkpoint 快照。

### 作品 02：MCP Server

```bash
# stdio 传输（本地 MCP 客户端接入用）
python 02-mcp-server/server.py

# Streamable HTTP 传输（远程部署用）
python 02-mcp-server/server.py --http
# 健康检查：http://127.0.0.1:8931/health
```

在支持 MCP 的客户端（如 Claude Desktop）中配置：

```json
{
  "mcpServers": {
    "qc-data-server": {
      "command": "python",
      "args": ["02-mcp-server/server.py"]
    }
  }
}
```

### 作品 03：SKILL.md
无需运行，直接展示。演示重点见仓库根目录 `README.md`。

### 作品 04：SDD 示例
无需运行，Markdown 文档。演示重点是"验收标准"那一段的写法。

## 三、接入真实模型（可选增强）

Agent 目前用确定性工具演示编排逻辑。要接真实模型：

```python
# 安装额外依赖
pip install langchain-openai

# 在 classify_node 后接入 LLM 节点
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(
    model="qwen-plus",                     # 或 gpt-4o 等
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key="...",                          # 用环境变量注入，不要硬编码
    temperature=0,
)
```

**接入时要注意的三点**：
1. **分类任务用 temperature=0 + 结构化输出**，不要只靠提示词要求 JSON；
2. **模型分级路由**：分类/抽取用小模型，复杂推理才上大模型，通常省 60% 以上成本；
3. **加 max_tokens 与超时**：LLM 调用是网络操作，必须有超时与重试（区分 429 可重试、内容过滤不可重试）。
