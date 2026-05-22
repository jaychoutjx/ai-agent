"""
LangGraph Agent 的状态定义。

【面试必讲】LangGraph 的核心思想：
- 把 Agent 的执行过程建模成一张"状态图"（StateGraph）
- 节点（Node）：一个执行单元（如 Router、Tool、Synthesizer）
- 边（Edge）：节点之间的流转（条件边可以根据状态分支）
- 状态（State）：整张图共享的数据（消息列表、中间结果等）

【为什么用 LangGraph 而不是手写循环？】
1. 显式状态机：执行流程可视化，调试方便
2. 内置 Checkpoint：支持恢复执行（人工介入场景）
3. 流式输出：每个节点的执行结果都能流式推到前端
4. 时间旅行：可以回到任意中间状态重新执行
5. 业界主流：2025 年起 LangChain 团队主推的 Agent 框架
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.schemas.document import Citation


class ToolCallRecord(TypedDict):
    """单次工具调用的记录（用于前端展示）。"""

    tool_name: str
    arguments: dict
    result_summary: str  # 结果的简短摘要（避免太长）
    duration_ms: int


class AgentState(TypedDict, total=False):
    """
    Agent 的全局状态。

    每个字段含义：
    - messages: 对话历史（自带 reducer，新消息会追加而非覆盖）
    - question: 用户原始问题（不变）
    - history: 历史多轮对话
    - selected_doc_ids: 限定 RAG 检索范围
    - tool_calls: 所有工具调用记录（用于前端展示思考过程）
    - citations: RAG 命中的引用片段（最终答案展示用）
    - iterations: 当前已经迭代了多少轮（防止死循环）
    - final_answer: 最终答案（被 Synthesizer 设置）
    """

    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    history: list[dict]
    selected_doc_ids: list[str] | None
    tool_calls: list[ToolCallRecord]
    citations: list[Citation]
    iterations: int
    final_answer: str | None
