"""
LangGraph Agent 主图。

【架构】
                ┌──────────────┐
                │   START      │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │  agent (LLM) │  ← 决策：要么调工具，要么直接答
                └──────┬───────┘
                       ↓
                  条件分支:
        ┌──────────────┴──────────────┐
        │ has tool_calls?             │
        ↓                              ↓
  ┌──────────┐                  ┌──────────┐
  │  tools   │ ── 执行工具 ──→  │   END    │ ← 没工具调用，直接结束
  └────┬─────┘                  └──────────┘
       │
       └────────────→ 返回 agent（继续决策）

【面试可讲】
- 用 LangGraph 的 ToolNode 简化工具执行（自动处理 ToolCall → 工具调用 → ToolMessage）
- 用 bind_tools() 让 LLM 知道有哪些工具可用，触发 Function Calling
- 条件边（add_conditional_edges）根据状态决定下一步走哪
- MAX_ITERATIONS 防止 Agent 死循环（生产必备）
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.core.logger import logger
from app.schemas.document import Citation
from app.services.agent.state import AgentState, ToolCallRecord
from app.services.agent.tools import (
    ALL_TOOLS,
    get_call_context,
    set_call_context,
)
from app.services.llm.chat_model import get_chat_model

MAX_ITERATIONS = 6  # 防止死循环


AGENT_SYSTEM_PROMPT = """你是一个专业的 AI 助手，能够调用以下工具来帮助回答问题：

【可用工具】
- search_knowledge_base: 检索企业私有知识库（用户上传的文档）
- web_search:           联网搜索最新信息
- calculator:           精确数学计算
- get_current_time:     获取当前日期时间

【决策原则】
1. 优先尝试 search_knowledge_base：如果问题可能与用户文档相关
2. 涉及"今天/现在/最新"等时效性问题：先调用 get_current_time
3. 涉及精确数字计算：必须用 calculator，**不要自己心算**
4. 知识库找不到 + 涉及外部信息：用 web_search 兜底
5. 简单的常识问答（不需要工具）：直接回答即可，不要硬调用工具
6. 一次性调用多个工具时使用并行调用（同一轮里返回多个 tool_calls）
7. 综合所有工具结果，用中文 Markdown 给出最终答案

【回答规范】
- 简洁清晰，不啰嗦
- 涉及代码用代码块
- **不要**在正文里插入 `[1]`、`[2]`、`【1】` 之类的引用编号；
  前端会单独以"参考来源"卡片展示引用，无需在文中重复标注
"""


def _build_llm_with_tools():
    """绑定工具到 LLM。这一步让 LLM 知道有哪些工具可调，并能触发 Function Calling。"""
    llm = get_chat_model(temperature=0.2, streaming=True)
    return llm.bind_tools(ALL_TOOLS)


# ============================================================
# 节点 1: agent —— LLM 决策（要么调工具，要么直接答）
# ============================================================
async def agent_node(state: AgentState) -> dict[str, Any]:
    """
    Agent 节点：调用 LLM 决策。

    返回的 messages 会被 add_messages reducer 追加到 state["messages"]。
    """
    iterations = state.get("iterations", 0)
    if iterations >= MAX_ITERATIONS:
        logger.warning(f"达到最大迭代次数 {MAX_ITERATIONS}，强制结束")
        return {
            "messages": [
                AIMessage(
                    content="（已达到最大思考轮数。请重新提问或简化问题。）"
                )
            ],
            "iterations": iterations + 1,
        }

    llm = _build_llm_with_tools()
    msgs = state["messages"]

    # 第一次进 agent 节点时，确保有 system message
    if not msgs or not isinstance(msgs[0], SystemMessage):
        msgs = [SystemMessage(content=AGENT_SYSTEM_PROMPT), *msgs]

    response = await llm.ainvoke(msgs)
    return {
        "messages": [response],
        "iterations": iterations + 1,
    }


# ============================================================
# 节点 2: tools —— 用 ToolNode 执行工具
# ============================================================
class TrackedToolNode(ToolNode):
    """
    继承 ToolNode，在执行工具前后记录到 state["tool_calls"]，
    便于前端展示"思考过程"。
    """

    async def ainvoke(  # type: ignore[override]
        self,
        input: AgentState,
        config=None,
        **kwargs,
    ) -> dict[str, Any]:
        last_msg = input["messages"][-1]
        tool_calls = getattr(last_msg, "tool_calls", []) or []

        records: list[ToolCallRecord] = list(input.get("tool_calls", []))
        starts: dict[str, float] = {tc["id"]: time.perf_counter() for tc in tool_calls}

        result = await super().ainvoke(input, config=config, **kwargs)

        # 把每个 ToolMessage 转成 record
        for msg in result.get("messages", []):
            if isinstance(msg, ToolMessage):
                tc_id = msg.tool_call_id
                tc_match = next(
                    (tc for tc in tool_calls if tc["id"] == tc_id), None
                )
                if tc_match:
                    duration_ms = int(
                        (time.perf_counter() - starts.get(tc_id, time.perf_counter()))
                        * 1000
                    )
                    summary = str(msg.content)
                    if len(summary) > 200:
                        summary = summary[:200] + "..."
                    records.append(
                        ToolCallRecord(
                            tool_name=tc_match["name"],
                            arguments=tc_match.get("args", {}),
                            result_summary=summary,
                            duration_ms=duration_ms,
                        )
                    )

        result["tool_calls"] = records
        return result


# ============================================================
# 条件边：决定 agent 节点之后走哪
# ============================================================
def should_continue(state: AgentState) -> str:
    """
    判断是继续调工具还是结束。
    - 如果最后一条 AI 消息有 tool_calls → 走 tools 节点
    - 否则 → END
    """
    if state.get("iterations", 0) >= MAX_ITERATIONS:
        return END

    msgs = state["messages"]
    if not msgs:
        return END

    last = msgs[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


# ============================================================
# 构建 Graph
# ============================================================
def build_agent_graph():
    """构建并编译 LangGraph。"""
    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", TrackedToolNode(ALL_TOOLS))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END},
    )
    graph.add_edge("tools", "agent")  # 工具执行完后回到 agent 继续决策

    compiled = graph.compile()
    return compiled


# 单例
_compiled_graph = None


def get_agent_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agent_graph()
    return _compiled_graph


# ============================================================
# 流式执行入口（API 层调用）
# ============================================================
async def run_agent_stream(
    question: str,
    history: list[dict] | None = None,
    selected_doc_ids: list[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    流式运行 Agent，把每一步的进度推给前端。

    Yields 的事件类型：
    - {"type": "step", "node": "agent" | "tools", ...}：节点开始
    - {"type": "tool_call", "tool_name": "...", "arguments": {...}}：检测到工具调用
    - {"type": "tool_result", "tool_name": "...", "summary": "..."}：工具执行完毕
    - {"type": "content", "content": "..."}：最终回答的流式内容
    - {"type": "citations", "citations": [...]}：RAG 引用
    - {"type": "done"}：结束
    """
    # 设置工具调用上下文（让 search_knowledge_base 知道限定哪些文档）
    set_call_context(
        selected_doc_ids=selected_doc_ids,
        collected_citations=[],
    )

    # 构造 HumanMessage（含历史对话）
    msgs: list[BaseMessage] = []
    if history:
        for h in history:
            role = h.get("role")
            content = h.get("content", "")
            if role == "user":
                msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                msgs.append(AIMessage(content=content))
    msgs.append(HumanMessage(content=question))

    initial_state: AgentState = {
        "messages": msgs,
        "question": question,
        "history": history or [],
        "selected_doc_ids": selected_doc_ids,
        "tool_calls": [],
        "citations": [],
        "iterations": 0,
        "final_answer": None,
    }

    graph = get_agent_graph()

    # 用 astream_events 拿到细粒度事件
    seen_tool_calls: set[str] = set()
    final_text_started = False

    async for event in graph.astream_events(initial_state, version="v2"):
        kind = event.get("event", "")
        name = event.get("name", "")

        # 节点开始
        if kind == "on_chain_start" and name in ("agent", "tools"):
            yield {"type": "step", "node": name}

        # LLM 流式 token
        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if not isinstance(chunk, AIMessageChunk):
                continue

            # 检测到 tool_call_chunks（说明这一轮在调工具，不要把 chunk 当文字推给前端）
            if chunk.tool_call_chunks:
                continue

            # 是否是"最终回答"阶段（没有 tool_calls，开始流式吐文本）
            if chunk.content:
                if not final_text_started:
                    final_text_started = True
                yield {"type": "content", "content": chunk.content}

        # 节点完成时检查是否有新的工具调用
        if kind == "on_chain_end" and name == "agent":
            output = event["data"].get("output", {}) or {}
            new_msgs = output.get("messages", [])
            for m in new_msgs:
                if isinstance(m, AIMessage) and m.tool_calls:
                    for tc in m.tool_calls:
                        tcid = tc.get("id", "")
                        if tcid in seen_tool_calls:
                            continue
                        seen_tool_calls.add(tcid)
                        yield {
                            "type": "tool_call",
                            "tool_name": tc.get("name", ""),
                            "arguments": tc.get("args", {}),
                        }

        if kind == "on_chain_end" and name == "tools":
            output = event["data"].get("output", {}) or {}
            new_msgs = output.get("messages", [])
            for m in new_msgs:
                if isinstance(m, ToolMessage):
                    summary = str(m.content)
                    if len(summary) > 200:
                        summary = summary[:200] + "..."
                    yield {
                        "type": "tool_result",
                        "tool_name": m.name or "",
                        "summary": summary,
                    }

    # 最后推 citations（如果有）
    collected = get_call_context().get("collected_citations") or []
    if collected:
        citations: list[Citation] = []
        seen_chunk_ids = set()
        for r in collected:
            if r.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(r.chunk_id)
            citations.append(
                Citation(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    document_name=r.document_name or "未知文档",
                    content=r.content,
                    score=r.final_score,
                    chunk_index=r.chunk_index,
                )
            )
        yield {"type": "citations", "citations": [c.model_dump() for c in citations]}

    yield {"type": "done"}
