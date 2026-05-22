"""
聊天 API 路由。

实现两个端点：
1. POST /api/v1/chat/completions      - 非流式（一次性返回）
2. POST /api/v1/chat/completions/stream - SSE 流式（打字机效果）

【面试必讲】为什么用 SSE 而不是 WebSocket？
- SSE 单向（服务端→客户端）即可，简单
- 自动重连
- 走 HTTP，穿透防火墙友好
- 浏览器原生支持 EventSource
- LLM 流式场景标配（OpenAI、Claude 都用 SSE）
"""

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.logger import logger
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm.chains import build_chat_chain

router = APIRouter()


def _convert_history(history: list) -> list:
    """把 Pydantic ChatMessage 列表转成 LangChain 的 Message 对象列表。"""
    msg_map = {"user": HumanMessage, "assistant": AIMessage, "system": SystemMessage}
    return [msg_map[m.role](content=m.content) for m in history]


@router.post("/completions", response_model=ChatResponse)
async def chat_completions(req: ChatRequest) -> ChatResponse:
    """非流式聊天。一次性返回完整答案。"""
    try:
        chain = build_chat_chain()
        result = await chain.ainvoke(
            {"history": _convert_history(req.history), "input": req.message}
        )
        return ChatResponse(content=result, model=settings.qwen_chat_model)
    except Exception as e:
        logger.exception(f"chat_completions error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/completions/stream")
async def chat_completions_stream(req: ChatRequest):
    """
    SSE 流式聊天。前端用 EventSource 接收。

    每个 chunk 都是一个 SSE event：
        data: {"content": "你"}
        data: {"content": "好"}
        data: [DONE]
    """

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            chain = build_chat_chain()

            async for chunk in chain.astream(
                {"history": _convert_history(req.history), "input": req.message}
            ):
                if chunk:
                    yield {"data": json.dumps({"content": chunk}, ensure_ascii=False)}

            yield {"data": "[DONE]"}
        except Exception as e:
            logger.exception(f"stream error: {e}")
            yield {"data": json.dumps({"error": str(e)}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())
