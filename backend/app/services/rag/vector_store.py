"""
Milvus 向量库封装（基于 pymilvus 官方推荐的 MilvusClient）。

【为什么不用 langchain-milvus？】
- langchain-milvus 1.x 内部仍混用 ORM API（Collection），与 pymilvus 2.6 有连接 alias 兼容问题
- 直接使用 MilvusClient 更稳定、API 更现代、类型注解更友好
- 自己控制 schema 也更适合面试讲解（"我自己设计了 Collection 结构"）

【Collection Schema 设计】
| 字段           | 类型           | 说明                                 |
|----------------|----------------|--------------------------------------|
| id             | VARCHAR (PK)   | 分块 ID（如 doc-uuid_0_xxx）         |
| embedding      | FLOAT_VECTOR   | 1024 维向量                          |
| content        | VARCHAR(8192)  | 分块原文（方便检索后直接拿）          |
| document_id    | VARCHAR(64)    | 所属文档 ID                          |
| document_name  | VARCHAR(512)   | 文档名（前端引用展示）                |
| chunk_index    | INT64          | 在原文档中的序号                      |

【索引】
- 类型: HNSW（高召回 + 高速度）
- 度量: COSINE（语义检索标配）
- 参数: M=16, efConstruction=200（生产推荐值）
"""

import asyncio
from functools import lru_cache
from typing import Any

from langchain_core.documents import Document as LCDocument
from pymilvus import DataType, MilvusClient

from app.core.config import settings
from app.core.logger import logger
from app.services.llm.embedding import get_embedding_model

COLLECTION_NAME = settings.milvus_collection
EMBEDDING_DIM = settings.embedding_dim


def _build_milvus_uri() -> str:
    """本地 Milvus 模式的 URI。"""
    return f"http://{settings.milvus_host}:{settings.milvus_port}"


def _is_zilliz_cloud() -> bool:
    """是否走 Zilliz Cloud（云端托管）。"""
    return bool(settings.milvus_uri and settings.milvus_token)


@lru_cache(maxsize=1)
def get_milvus_client() -> MilvusClient:
    """
    单例 MilvusClient。

    - 配置了 MILVUS_URI + MILVUS_TOKEN  → 走 Zilliz Cloud（HTTPS + Token 鉴权）
    - 否则                              → 走本地 Milvus（HTTP 无鉴权）
    """
    if _is_zilliz_cloud():
        # Zilliz Cloud：传 uri + token，pymilvus 会自动 HTTPS + Bearer Token
        uri = settings.milvus_uri
        logger.info(f"连接 Zilliz Cloud: {uri}")
        client = MilvusClient(uri=uri, token=settings.milvus_token)
    else:
        # 本地 Milvus
        uri = _build_milvus_uri()
        logger.info(f"连接本地 Milvus: {uri}")
        client = MilvusClient(uri=uri)

    _ensure_collection(client)
    return client


def _ensure_collection(client: MilvusClient) -> None:
    """确保 Collection 存在并已加载到内存。"""
    if client.has_collection(COLLECTION_NAME):
        # 已存在，确保已 load（Milvus 重启后或首次连接需要 load 才能 search）
        try:
            state = client.get_load_state(collection_name=COLLECTION_NAME)
            state_str = str(state.get("state", state)) if isinstance(state, dict) else str(state)
            if "Loaded" not in state_str:
                logger.info(f"加载 Collection 到内存: {COLLECTION_NAME}")
                client.load_collection(COLLECTION_NAME)
            else:
                logger.info(f"Collection 已存在且已加载: {COLLECTION_NAME}")
        except Exception:
            # 兼容老 Milvus：直接 load 一次（重复 load 是幂等的）
            logger.info(f"加载 Collection 到内存: {COLLECTION_NAME}")
            client.load_collection(COLLECTION_NAME)
        return

    logger.info(f"创建 Collection: {COLLECTION_NAME}")

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=128)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
    schema.add_field("content", DataType.VARCHAR, max_length=8192)
    schema.add_field("document_id", DataType.VARCHAR, max_length=64)
    schema.add_field("document_name", DataType.VARCHAR, max_length=512)
    schema.add_field("chunk_index", DataType.INT64)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )

    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=schema,
        index_params=index_params,
    )
    client.load_collection(COLLECTION_NAME)
    logger.info(f"Collection 创建并加载完成: {COLLECTION_NAME}")


def _truncate(text: str, max_len: int = 8000) -> str:
    """截断文本到 Milvus VARCHAR 字段允许的长度内（保险起见留余量）。"""
    return text[:max_len] if len(text) > max_len else text


# 阿里云百炼 text-embedding-v3 单次最多接受 10 条文本（硬限制）。
# 我们以这个为上限做分批；如果以后切换到其他 embedding 接口，调整这里即可。
EMBEDDING_BATCH_SIZE = 10


async def _embed_in_batches(texts: list[str]) -> list[list[float]]:
    """
    分批 embedding（避开百炼 batch_size <= 10 的限制），并发跑所有批次。

    【为什么不用 LangChain OpenAIEmbeddings 自带的 chunk_size？】
    - LangChain 默认 chunk_size=1000，是针对 OpenAI 设计的
    - 即使我们把 chunk_size 改成 10，它内部依旧是串行循环，速度慢
    - 我们用 asyncio.gather 并发跑，N 批同时打到百炼，吞吐快好几倍
    """
    if not texts:
        return []

    embedding_model = get_embedding_model()

    batches: list[list[str]] = [
        texts[i : i + EMBEDDING_BATCH_SIZE]
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE)
    ]

    if len(batches) == 1:
        return await embedding_model.aembed_documents(batches[0])

    logger.info(
        f"Embedding 分批: 共 {len(texts)} 条文本，"
        f"分 {len(batches)} 批并发执行（每批 ≤ {EMBEDDING_BATCH_SIZE}）"
    )
    results = await asyncio.gather(
        *(embedding_model.aembed_documents(b) for b in batches)
    )
    flat: list[list[float]] = []
    for r in results:
        flat.extend(r)
    return flat


async def add_chunks(chunks: list[LCDocument], ids: list[str]) -> list[str]:
    """
    批量入库分块。

    流程：
    1. 文本分批 Embedding（百炼限制每批 ≤ 10 条，并发跑）
    2. 拼成 Milvus 行 → 批量 insert

    Args:
        chunks: LangChain Document 列表，metadata 必须包含 document_id/document_name/chunk_index
        ids:    与 chunks 一一对应的主键 ID

    Returns:
        实际入库的 ID 列表
    """
    if not chunks:
        return []
    assert len(chunks) == len(ids), "chunks 和 ids 长度必须一致"

    client = get_milvus_client()

    texts = [c.page_content for c in chunks]
    vectors = await _embed_in_batches(texts)

    rows: list[dict[str, Any]] = []
    for cid, chunk, vec in zip(ids, chunks, vectors, strict=True):
        meta = chunk.metadata or {}
        rows.append(
            {
                "id": cid,
                "embedding": vec,
                "content": _truncate(chunk.page_content),
                "document_id": str(meta.get("document_id", "")),
                "document_name": _truncate(str(meta.get("document_name", "")), 500),
                "chunk_index": int(meta.get("chunk_index", 0)),
            }
        )

    # MilvusClient.insert 是同步方法，丢到线程池避免阻塞事件循环
    await asyncio.to_thread(
        client.insert, collection_name=COLLECTION_NAME, data=rows
    )
    logger.info(f"入库完成: {len(rows)} 个分块")
    return ids


async def search(
    query: str,
    top_k: int = 5,
    document_ids: list[str] | None = None,
) -> list[tuple[LCDocument, float]]:
    """
    向量检索。

    Args:
        query:        用户问题文本（自动 Embedding）
        top_k:        召回数量
        document_ids: 限定检索的文档 ID；None=全库检索

    Returns:
        [(LCDocument, 相关度分数), ...] 按相关度从高到低排序
    """
    client = get_milvus_client()
    embedding_model = get_embedding_model()

    query_vec = await embedding_model.aembed_query(query)

    filter_expr = ""
    if document_ids:
        ids_str = ", ".join(f'"{did}"' for did in document_ids)
        filter_expr = f"document_id in [{ids_str}]"

    search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

    raw = await asyncio.to_thread(
        client.search,
        collection_name=COLLECTION_NAME,
        data=[query_vec],
        anns_field="embedding",
        limit=top_k,
        filter=filter_expr,
        search_params=search_params,
        output_fields=["content", "document_id", "document_name", "chunk_index"],
    )

    results: list[tuple[LCDocument, float]] = []
    if raw and raw[0]:
        for hit in raw[0]:
            entity = hit.get("entity", {})
            doc = LCDocument(
                page_content=entity.get("content", ""),
                metadata={
                    "id": hit.get("id"),
                    "document_id": entity.get("document_id", ""),
                    "document_name": entity.get("document_name", ""),
                    "chunk_index": entity.get("chunk_index", 0),
                },
            )
            # COSINE 距离已经是相似度（越大越相似），直接用即可
            score = float(hit.get("distance", 0.0))
            results.append((doc, score))

    logger.info(
        f"检索完成: query={query[:30]}..., top_k={top_k}, 命中 {len(results)} 条"
    )
    return results


async def delete_by_document(document_id: str) -> int:
    """删除某个文档的所有分块。返回是否成功（1/0）。"""
    client = get_milvus_client()
    try:
        await asyncio.to_thread(
            client.delete,
            collection_name=COLLECTION_NAME,
            filter=f'document_id == "{document_id}"',
        )
        logger.info(f"删除文档分块: document_id={document_id}")
        return 1
    except Exception as e:
        logger.error(f"删除失败: {e}")
        return 0


async def count_chunks(document_id: str | None = None) -> int:
    """统计分块总数（或某个文档的分块数）。便于调试。"""
    client = get_milvus_client()
    filter_expr = f'document_id == "{document_id}"' if document_id else ""
    res = await asyncio.to_thread(
        client.query,
        collection_name=COLLECTION_NAME,
        filter=filter_expr,
        output_fields=["count(*)"],
    )
    if res and "count(*)" in res[0]:
        return int(res[0]["count(*)"])
    return 0


def get_vector_store():
    """兼容旧接口（保留 import 不变）。新代码请直接调用 add_chunks/search。"""
    return get_milvus_client()
