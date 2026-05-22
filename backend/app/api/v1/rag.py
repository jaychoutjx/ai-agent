"""
RAG 问答 API。

端点：
- POST /api/v1/rag/query           - 非流式（含完整引用）
- POST /api/v1/rag/query/stream    - SSE 流式（先推 citations 再推内容）
"""

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.logger import logger
from app.schemas.document import RagQueryRequest, RagQueryResponse
from app.services.rag.advanced_retrieval import RagConfig
from app.services.rag.retrieval import rag_answer, rag_answer_stream


def _build_config(req: RagQueryRequest) -> RagConfig:
    """从请求构建 RagConfig。"""
    return RagConfig(
        top_k=req.top_k,
        candidate_k=max(req.top_k * 4, 20),
        use_bm25=req.use_bm25,
        use_rerank=req.use_rerank,
        use_multi_query=req.use_multi_query,
        use_hyde=req.use_hyde,
    )

router = APIRouter()


@router.post("/query", response_model=RagQueryResponse)
async def rag_query(req: RagQueryRequest) -> RagQueryResponse:
    """非流式 RAG 问答。"""
    try:
        answer, citations = await rag_answer(
            question=req.question,
            top_k=req.top_k,
            document_ids=req.document_ids,
            config=_build_config(req),
        )
        return RagQueryResponse(
            answer=answer,
            citations=citations,
            model=settings.qwen_chat_model,
        )
    except Exception as e:
        logger.exception(f"RAG 查询失败: {e}")
        raise HTTPException(500, str(e)) from e


@router.post("/query/stream")
async def rag_query_stream(req: RagQueryRequest):
    """
    SSE 流式 RAG 问答。

    SSE 事件序列：
        data: {"type":"citations","citations":[...]}     # 先推引用
        data: {"type":"content","content":"基于"}         # 然后流式推内容
        data: {"type":"content","content":"资料..."}
        ...
        data: [DONE]
    """

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            stream, citations = await rag_answer_stream(
                question=req.question,
                top_k=req.top_k,
                document_ids=req.document_ids,
                config=_build_config(req),
            )

            # 1) 先推 citations，让前端立即展示引用面板
            yield {
                "data": json.dumps(
                    {
                        "type": "citations",
                        "citations": [c.model_dump() for c in citations],
                    },
                    ensure_ascii=False,
                )
            }

            # 2) 流式推回答内容
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
            logger.exception(f"RAG 流式查询失败: {e}")
            yield {
                "data": json.dumps(
                    {"type": "error", "error": str(e)}, ensure_ascii=False
                )
            }

    return EventSourceResponse(event_generator())
