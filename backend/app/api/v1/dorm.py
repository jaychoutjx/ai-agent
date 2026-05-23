"""
寝室群聊 RAG 接口。

【访问保护】
所有 /dorm/* 接口都需要请求头 `X-Dorm-Token: <DORM_ACCESS_TOKEN>`，
配置中 DORM_ACCESS_TOKEN 为空时，整组接口直接 403。

接口列表：
- GET  /api/v1/dorm/health           - 探测是否已配置（前端用来决定是否展示入口）
- GET  /api/v1/dorm/stats            - 数据集统计（成员、时间范围、会话块数）
- POST /api/v1/dorm/query/stream     - 流式问答（带时间/参与者过滤）
- POST /api/v1/dorm/summary          - 群聊周报/月报（非流式，因为是 Map-Reduce）
- POST /api/v1/dorm/imitate/stream   - 风格模仿（流式）
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Header, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.logger import logger
from app.schemas.dorm import (
    DormImitateRequest,
    DormQueryRequest,
    DormStatsResponse,
    DormSummaryRequest,
)
from app.services.dorm.service import (
    dorm_imitate,
    dorm_query_stream,
    dorm_summary,
)
from app.services.dorm.vector_store import count_sessions, get_dorm_client

router = APIRouter()


def _check_token(token: str | None) -> None:
    """寝室口令鉴权。空 token 配置 = 该模式整体关闭。"""
    if not settings.dorm_access_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="dorm 模式未启用",
        )
    if token != settings.dorm_access_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="访问口令错误",
        )


@router.get("/health")
async def dorm_health(x_dorm_token: str | None = Header(default=None)) -> dict:
    """
    前端启动时用来判断"是否展示寝室 tab"。

    返回：
        - enabled: 后端有没有配置 DORM_ACCESS_TOKEN
        - authenticated: 用户当前 token 对不对
    """
    enabled = bool(settings.dorm_access_token)
    authenticated = enabled and (x_dorm_token == settings.dorm_access_token)
    return {"enabled": enabled, "authenticated": authenticated}


@router.get("/stats", response_model=DormStatsResponse)
async def dorm_stats(x_dorm_token: str | None = Header(default=None)):
    """数据集统计：会话块数、时间范围、成员等。"""
    _check_token(x_dorm_token)

    client = get_dorm_client()
    if not client.has_collection(settings.dorm_collection):
        return DormStatsResponse(
            total_sessions=0,
            total_messages=0,
            members=[],
            time_range={"start": None, "end": None},
        )

    total = await count_sessions()
    if total == 0:
        return DormStatsResponse(
            total_sessions=0,
            total_messages=0,
            members=[],
            time_range={"start": None, "end": None},
        )

    # 拿全部块算统计（量级 < 5000，单次 query 没问题）
    import asyncio as _asyncio

    raw = await _asyncio.to_thread(
        client.query,
        collection_name=settings.dorm_collection,
        filter="",
        output_fields=["start_time", "end_time", "participants", "msg_count"],
        limit=5000,
    )
    msg_total = sum(int(r.get("msg_count", 0)) for r in raw)
    # 成员发言计数
    member_count: dict[str, int] = {}
    times: list[str] = []
    for r in raw:
        times.append(r.get("start_time", ""))
        msg_n = int(r.get("msg_count", 0))
        for p in (r.get("participants", "") or "").split(","):
            p = p.strip()
            if not p:
                continue
            member_count[p] = member_count.get(p, 0) + msg_n
    members = [
        {"name": k, "message_count": v, "avg_length": 0}
        for k, v in sorted(member_count.items(), key=lambda x: -x[1])
    ]
    times.sort()
    time_range = {"start": times[0] if times else None, "end": times[-1] if times else None}

    return DormStatsResponse(
        total_sessions=total,
        total_messages=msg_total,
        members=members,
        time_range=time_range,
    )


@router.post("/query/stream")
async def dorm_query_stream_endpoint(
    req: DormQueryRequest,
    x_dorm_token: str | None = Header(default=None),
):
    """流式 RAG 问答。"""
    _check_token(x_dorm_token)

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            stream, citations = await dorm_query_stream(
                question=req.question,
                top_k=req.top_k,
                start_date=req.start_date,
                end_date=req.end_date,
                participants=req.participants,
            )
            yield {
                "data": json.dumps(
                    {
                        "type": "citations",
                        "citations": [c.model_dump() for c in citations],
                    },
                    ensure_ascii=False,
                )
            }
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
            logger.exception(f"[dorm-query] 失败: {e}")
            yield {
                "data": json.dumps(
                    {"type": "error", "error": str(e)}, ensure_ascii=False
                )
            }

    return EventSourceResponse(event_generator())


@router.post("/summary")
async def dorm_summary_endpoint(
    req: DormSummaryRequest,
    x_dorm_token: str | None = Header(default=None),
):
    """生成群聊周报 / 月报（非流式：Map-Reduce 内部已并发）。"""
    _check_token(x_dorm_token)
    try:
        report = await dorm_summary(range_=req.range, end_date=req.end_date)
        return {"report": report, "range": req.range, "end_date": req.end_date}
    except Exception as e:
        logger.exception(f"[dorm-summary] 失败: {e}")
        raise HTTPException(500, str(e)) from e


@router.post("/imitate/stream")
async def dorm_imitate_stream_endpoint(
    req: DormImitateRequest,
    x_dorm_token: str | None = Header(default=None),
):
    """流式：模仿某成员的风格回复。"""
    _check_token(x_dorm_token)

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            stream = await dorm_imitate(
                target_member=req.target_member,
                user_message=req.user_message,
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
            logger.exception(f"[dorm-imitate] 失败: {e}")
            yield {
                "data": json.dumps(
                    {"type": "error", "error": str(e)}, ensure_ascii=False
                )
            }

    return EventSourceResponse(event_generator())
