"""
寝室群聊专属 Milvus collection。

【为什么独立 collection 而不是复用知识库的？】
1. 物理隔离：寝室数据是私密的，绝不能和公开知识库混在一起被检索到
2. Schema 不同：会话块需要带 start_ts/end_ts/participants 等元数据，
   方便做时间范围筛选和参与者筛选
3. 索引参数可独立调优：聊天数据的检索特征和文档不一样，HNSW 参数后期可微调

【面试可讲】这是典型的"多租户/多场景下的向量库设计权衡"——
能不能用一个大表搞定？技术上能（加 source 字段过滤），
但**逻辑隔离 + 性能可独立调优**是更专业的做法。
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

from pymilvus import DataType, MilvusClient

from app.core.config import settings
from app.core.logger import logger
from app.schemas.dorm import DormCitation, DormSession
from app.services.llm.embedding import get_embedding_model
from app.services.rag.vector_store import (
    EMBEDDING_BATCH_SIZE,
    _embed_in_batches,  # 复用现有的并发分批 embedding 实现
)

DORM_COLLECTION = settings.dorm_collection
EMBEDDING_DIM = settings.embedding_dim


def _build_milvus_uri() -> str:
    return f"http://{settings.milvus_host}:{settings.milvus_port}"


def _is_zilliz_cloud() -> bool:
    return bool(settings.milvus_uri and settings.milvus_token)


@lru_cache(maxsize=1)
def get_dorm_client() -> MilvusClient:
    """复用 Milvus 连接配置，单例 client。"""
    if _is_zilliz_cloud():
        client = MilvusClient(uri=settings.milvus_uri, token=settings.milvus_token)
        logger.info(f"[dorm] 连接 Zilliz Cloud: {settings.milvus_uri}")
    else:
        client = MilvusClient(uri=_build_milvus_uri())
        logger.info(f"[dorm] 连接本地 Milvus")

    _ensure_collection(client)
    return client


def _ensure_collection(client: MilvusClient) -> None:
    """确保 dorm collection 存在并已加载到内存。"""
    if client.has_collection(DORM_COLLECTION):
        try:
            state = client.get_load_state(collection_name=DORM_COLLECTION)
            state_str = (
                str(state.get("state", state)) if isinstance(state, dict) else str(state)
            )
            if "Loaded" not in state_str:
                client.load_collection(DORM_COLLECTION)
                logger.info(f"[dorm] 加载 collection: {DORM_COLLECTION}")
        except Exception:
            client.load_collection(DORM_COLLECTION)
        return

    logger.info(f"[dorm] 创建 collection: {DORM_COLLECTION}")
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("session_id", DataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
    schema.add_field("content", DataType.VARCHAR, max_length=8192)
    schema.add_field("start_time", DataType.VARCHAR, max_length=32)
    schema.add_field("end_time", DataType.VARCHAR, max_length=32)
    schema.add_field("start_ts", DataType.INT64)
    schema.add_field("end_ts", DataType.INT64)
    # 参与者列表用 JSON 字符串存储（VARCHAR 兼容性最好）
    schema.add_field("participants", DataType.VARCHAR, max_length=2048)
    schema.add_field("msg_count", DataType.INT64)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )

    client.create_collection(
        collection_name=DORM_COLLECTION,
        schema=schema,
        index_params=index_params,
    )
    client.load_collection(DORM_COLLECTION)
    logger.info(f"[dorm] collection 创建并加载完成: {DORM_COLLECTION}")


def _truncate(text: str, max_len: int = 8000) -> str:
    return text[:max_len] if len(text) > max_len else text


async def add_sessions(sessions: list[DormSession]) -> list[str]:
    """
    批量入库会话块（先 embedding 再 insert）。
    """
    if not sessions:
        return []

    client = get_dorm_client()
    texts = [s.content for s in sessions]
    vectors = await _embed_in_batches(texts)

    rows: list[dict[str, Any]] = []
    for s, vec in zip(sessions, vectors, strict=True):
        # 参与者用逗号串连存（前端展示也好用），并对极少数过长情况做兜底
        parts_str = ",".join(s.participants)
        rows.append(
            {
                "session_id": s.session_id,
                "embedding": vec,
                "content": _truncate(s.content),
                "start_time": s.start_time,
                "end_time": s.end_time,
                "start_ts": int(s.start_ts),
                "end_ts": int(s.end_ts),
                "participants": _truncate(parts_str, 2000),
                "msg_count": int(s.msg_count),
            }
        )

    # MilvusClient.insert 是同步方法，丢线程池
    # 一次 insert 太大 collection 可能超 gRPC 上限，分批
    BATCH = 200
    total = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i : i + BATCH]
        await asyncio.to_thread(
            client.insert, collection_name=DORM_COLLECTION, data=batch
        )
        total += len(batch)
        logger.info(f"[dorm] 已入库 {total}/{len(rows)} 块")

    logger.info(f"[dorm] 入库完成: 共 {len(rows)} 个会话块")
    return [s.session_id for s in sessions]


async def search_sessions(
    query: str,
    top_k: int = 8,
    start_ts: int | None = None,
    end_ts: int | None = None,
    participants: list[str] | None = None,
) -> list[DormCitation]:
    """语义检索会话块，支持时间范围 / 参与者过滤。"""
    client = get_dorm_client()
    embedding_model = get_embedding_model()
    qvec = await embedding_model.aembed_query(query)

    # 构造 filter 表达式
    exprs: list[str] = []
    if start_ts is not None:
        exprs.append(f"start_ts >= {start_ts}")
    if end_ts is not None:
        exprs.append(f"end_ts <= {end_ts}")
    if participants:
        # Milvus VARCHAR 不支持 contains，用 LIKE 凑活
        # 任一参与者匹配即命中
        like_clauses = " or ".join([f'participants like "%{p}%"' for p in participants])
        if like_clauses:
            exprs.append(f"({like_clauses})")
    filter_expr = " and ".join(exprs) if exprs else ""

    raw = await asyncio.to_thread(
        client.search,
        collection_name=DORM_COLLECTION,
        data=[qvec],
        anns_field="embedding",
        limit=top_k,
        filter=filter_expr,
        search_params={"metric_type": "COSINE", "params": {"ef": 64}},
        output_fields=[
            "session_id",
            "content",
            "start_time",
            "end_time",
            "participants",
            "msg_count",
        ],
    )

    citations: list[DormCitation] = []
    if raw and raw[0]:
        for hit in raw[0]:
            ent = hit.get("entity", {})
            parts_str = ent.get("participants", "")
            citations.append(
                DormCitation(
                    session_id=ent.get("session_id", hit.get("id", "")),
                    start_time=ent.get("start_time", ""),
                    end_time=ent.get("end_time", ""),
                    participants=[p for p in parts_str.split(",") if p],
                    content=ent.get("content", ""),
                    score=float(hit.get("distance", 0.0)),
                )
            )

    logger.info(
        f"[dorm] 检索完成: q={query[:30]}..., top_k={top_k}, 命中 {len(citations)}, "
        f"filter='{filter_expr}'"
    )
    return citations


async def query_by_time_range(
    start_ts: int,
    end_ts: int,
    limit: int = 1000,
) -> list[dict]:
    """按时间范围拉取会话块（用于"最近一周总结"这种场景）。"""
    client = get_dorm_client()
    raw = await asyncio.to_thread(
        client.query,
        collection_name=DORM_COLLECTION,
        filter=f"start_ts >= {start_ts} and end_ts <= {end_ts}",
        output_fields=[
            "session_id",
            "content",
            "start_time",
            "end_time",
            "participants",
            "msg_count",
        ],
        limit=limit,
    )
    # 按时间排序，方便 LLM 总结
    raw.sort(key=lambda r: r.get("start_time", ""))
    return raw


async def count_sessions() -> int:
    """统计 collection 中的会话块数。"""
    client = get_dorm_client()
    if not client.has_collection(DORM_COLLECTION):
        return 0
    res = await asyncio.to_thread(
        client.query,
        collection_name=DORM_COLLECTION,
        filter="",
        output_fields=["count(*)"],
    )
    if res and "count(*)" in res[0]:
        return int(res[0]["count(*)"])
    return 0


async def drop_collection() -> None:
    """删除整个 dorm collection（导入新数据前的清空操作）。"""
    client = get_dorm_client()
    if client.has_collection(DORM_COLLECTION):
        await asyncio.to_thread(client.drop_collection, DORM_COLLECTION)
        logger.warning(f"[dorm] 已删除 collection: {DORM_COLLECTION}")
        # 清缓存的 client（下次调用会自动重建 collection）
        get_dorm_client.cache_clear()


# 让 IDE/lint 知道我们刻意 import 了私有方法
_ = (EMBEDDING_BATCH_SIZE,)
