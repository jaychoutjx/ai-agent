"""
Agent API。

端点：
- POST /api/v1/agent/run/stream    - SSE 流式（推送节点进度 + 工具调用 + 内容）
"""

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.logger import logger
from app.schemas.agent import AgentRequest
from app.services.agent.graph import run_agent_stream

router = APIRouter()


@router.post("/run/stream")
async def agent_run_stream(req: AgentRequest):
    """
    SSE 流式 Agent 运行。

    事件序列示例：
        data: {"type":"step","node":"agent"}
        data: {"type":"tool_call","tool_name":"search_knowledge_base","arguments":{"query":"..."}}
        data: {"type":"tool_result","tool_name":"search_knowledge_base","summary":"..."}
        data: {"type":"step","node":"agent"}
        data: {"type":"content","content":"基于"}
        data: {"type":"content","content":"资料..."}
        data: {"type":"citations","citations":[...]}
        data: [DONE]
    """

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            async for event in run_agent_stream(
                question=req.question,
                history=req.history,
                selected_doc_ids=req.document_ids,
            ):
                if event.get("type") == "done":
                    yield {"data": "[DONE]"}
                    return
                yield {"data": json.dumps(event, ensure_ascii=False)}
        except Exception as e:
            logger.exception(f"Agent 运行失败: {e}")
            yield {
                "data": json.dumps(
                    {"type": "error", "error": str(e)}, ensure_ascii=False
                )
            }

    return EventSourceResponse(event_generator())
