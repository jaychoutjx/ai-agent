"""
拍照搜题接口。

接口列表：
- POST /api/v1/solve/stream  - 上传题目图片，流式返回识别 + 答案 + 解题步骤

数据走 JSON body（图片为 base64），不走 multipart，便于复用现有 SSE 客户端。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.logger import logger
from app.schemas.solve import SolveRequest
from app.services.solve.service import solve_question_stream

router = APIRouter()


@router.post("/stream")
async def solve_stream_endpoint(req: SolveRequest):
    """拍照搜题（流式）。

    SSE 事件序列：
        data: {"type":"content","content":"..."}   # 流式推送解题文本
        data: [DONE]
    """

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            stream = await solve_question_stream(
                image_base64=req.image_base64,
                subject=req.subject,
                extra=req.extra,
            )
            async for chunk in stream:
                if chunk:
                    yield {
                        "data": json.dumps(
                            {"type": "content", "content": chunk},
                            ensure_ascii=False,
                        )
                    }
            yield {"data": "[DONE]"}
        except Exception as e:
            logger.exception(f"[solve] 解题失败: {e}")
            yield {
                "data": json.dumps(
                    {"type": "error", "error": str(e)}, ensure_ascii=False
                )
            }

    return EventSourceResponse(event_generator())
