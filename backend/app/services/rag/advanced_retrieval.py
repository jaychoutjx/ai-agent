"""
高级 RAG 检索管道（可配置每项优化）。

【完整流程】
                                         ┌─→ Multi-Query / HyDE
用户问题 ──→ Query 改写（可选）──┤
                                         └─→ 原始问题
                       │
                       ↓ (对每个 query 跑)
            ┌──────────┴──────────┐
            ↓                      ↓
     向量检索 (top_k=20)    BM25 检索 (top_k=20)
            │                      │
            └──────────┬───────────┘
                       ↓
                 RRF 融合（Reciprocal Rank Fusion）
                       │
                       ↓
              候选集 (top_k=30)
                       │
                       ↓ (可选)
                  Reranker 重排
                       │
                       ↓
              最终 Top-K (默认 5)

【RRF 算法】
RRF (Reciprocal Rank Fusion) 是融合多路排序结果的简单有效算法：
    score(d) = Σ 1 / (k + rank_i(d))
其中 rank_i 是文档 d 在第 i 路排序中的位置（从 1 开始），k 通常取 60。

为什么用 RRF 而不是直接加权和？
- 不同检索器的分数尺度不同（向量是 0-1，BM25 是 0-100+），归一化困难
- RRF 只用排名，天然消除尺度问题
- 简单、稳定、效果好（论文证明）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from langchain_core.documents import Document as LCDocument

from app.core.logger import logger
from app.services.rag.bm25 import BM25Doc, get_bm25_retriever
from app.services.rag.query_rewrite import hyde_rewrite, multi_query_rewrite
from app.services.rag.reranker import get_reranker
from app.services.rag.vector_store import search as vector_search


@dataclass
class RagConfig:
    """RAG 检索配置（每项优化都可独立打开/关闭）。"""

    top_k: int = 5
    """最终返回数量"""

    candidate_k: int = 20
    """每路检索的候选数（粗排）"""

    use_bm25: bool = True
    """是否启用 BM25 关键词检索"""

    use_rerank: bool = True
    """是否启用 Reranker 重排"""

    use_multi_query: bool = False
    """是否启用 Multi-Query 改写"""

    multi_query_n: int = 2
    """Multi-Query 生成多少个变体"""

    use_hyde: bool = False
    """是否启用 HyDE（与 multi_query 二选一）"""

    rrf_k: int = 60
    """RRF 融合参数"""


@dataclass
class RetrievalResult:
    """单条检索结果。"""

    chunk_id: str
    content: str
    document_id: str
    document_name: str
    chunk_index: int
    # 各阶段的分数（便于前端调试）
    vector_score: float = 0.0
    bm25_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    final_score: float = 0.0
    # 一些调试信息
    matched_queries: list[str] = field(default_factory=list)


def _bm25_doc_to_result(doc: BM25Doc, score: float) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=doc.chunk_id,
        content=doc.content,
        document_id=doc.document_id,
        document_name=doc.document_name,
        chunk_index=doc.chunk_index,
        bm25_score=score,
    )


def _vector_doc_to_result(doc: LCDocument, score: float) -> RetrievalResult:
    meta = doc.metadata
    return RetrievalResult(
        chunk_id=str(meta.get("id", "")),
        content=doc.page_content,
        document_id=str(meta.get("document_id", "")),
        document_name=str(meta.get("document_name", "")),
        chunk_index=int(meta.get("chunk_index", 0)),
        vector_score=score,
    )


def _rrf_fuse(
    rankings: list[list[RetrievalResult]],
    k: int = 60,
) -> list[RetrievalResult]:
    """
    Reciprocal Rank Fusion。

    输入：多路排序结果（每路是一个 list，按相关度降序）
    输出：融合后的统一排序

    score(d) = Σ 1 / (k + rank_i(d))
    """
    fused: dict[str, RetrievalResult] = {}
    for ranking in rankings:
        for rank_idx, result in enumerate(ranking):
            cid = result.chunk_id
            inc = 1.0 / (k + rank_idx + 1)  # rank 从 1 开始

            if cid in fused:
                fused[cid].rrf_score += inc
                # 合并各路分数
                if result.vector_score > 0:
                    fused[cid].vector_score = max(
                        fused[cid].vector_score, result.vector_score
                    )
                if result.bm25_score > 0:
                    fused[cid].bm25_score = max(
                        fused[cid].bm25_score, result.bm25_score
                    )
            else:
                fused[cid] = RetrievalResult(
                    chunk_id=result.chunk_id,
                    content=result.content,
                    document_id=result.document_id,
                    document_name=result.document_name,
                    chunk_index=result.chunk_index,
                    vector_score=result.vector_score,
                    bm25_score=result.bm25_score,
                    rrf_score=inc,
                )

    sorted_results = sorted(fused.values(), key=lambda r: r.rrf_score, reverse=True)
    return sorted_results


async def _retrieve_for_single_query(
    query: str,
    config: RagConfig,
    document_ids: list[str] | None,
) -> list[RetrievalResult]:
    """对单个 query 跑向量 + BM25 检索 + RRF 融合。"""
    # 并发跑两路
    tasks = [vector_search(query, top_k=config.candidate_k, document_ids=document_ids)]
    if config.use_bm25:
        tasks.append(
            get_bm25_retriever().search(
                query, top_k=config.candidate_k, document_ids=document_ids
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 容错：某一路挂了不影响整体
    rankings: list[list[RetrievalResult]] = []
    vec_raw = results[0] if not isinstance(results[0], Exception) else []
    rankings.append(
        [_vector_doc_to_result(doc, score) for doc, score in vec_raw]  # type: ignore[arg-type]
    )

    if config.use_bm25:
        bm25_raw = results[1] if not isinstance(results[1], Exception) else []
        rankings.append(
            [_bm25_doc_to_result(doc, score) for doc, score in bm25_raw]  # type: ignore[arg-type]
        )

    return _rrf_fuse(rankings, k=config.rrf_k)


async def advanced_retrieve(
    question: str,
    config: RagConfig | None = None,
    document_ids: list[str] | None = None,
) -> list[RetrievalResult]:
    """
    高级 RAG 检索主函数。

    Args:
        question: 用户问题
        config: 检索配置（每项优化可独立开关）
        document_ids: 限定检索的文档 ID

    Returns:
        Top-K 检索结果，按 final_score 降序
    """
    cfg = config or RagConfig()

    # ========== Step 1: Query 改写 ==========
    queries: list[str] = [question]
    if cfg.use_hyde:
        queries = [await hyde_rewrite(question)]
    elif cfg.use_multi_query:
        queries = await multi_query_rewrite(question, n=cfg.multi_query_n)

    logger.info(f"Step 1 Query 改写: {len(queries)} 个查询")

    # ========== Step 2: 多 Query 检索 + RRF 融合 ==========
    per_query_results = await asyncio.gather(
        *[_retrieve_for_single_query(q, cfg, document_ids) for q in queries]
    )

    # 把所有 query 的结果再融合一次（多 query 之间也用 RRF）
    if len(per_query_results) > 1:
        candidates = _rrf_fuse(per_query_results, k=cfg.rrf_k)
    else:
        candidates = per_query_results[0]

    logger.info(f"Step 2 粗排融合: 候选 {len(candidates)} 条")

    if not candidates:
        return []

    # ========== Step 3: Reranker 重排 ==========
    if cfg.use_rerank and len(candidates) > 1:
        # 取候选前 N（一般 30 左右），减少 Reranker 调用成本
        rerank_input = candidates[: max(cfg.top_k * 6, 30)]
        reranker = get_reranker()
        ranked = await reranker.rerank(
            query=question,  # Reranker 用原始问题（不用改写后的）
            documents=[r.content for r in rerank_input],
            top_n=cfg.top_k,
        )
        # 把 rerank 分数填进结果
        final: list[RetrievalResult] = []
        for orig_idx, rerank_score in ranked:
            r = rerank_input[orig_idx]
            r.rerank_score = rerank_score
            r.final_score = rerank_score
            final.append(r)
        logger.info(f"Step 3 Reranker 重排: {len(rerank_input)} → top_{cfg.top_k}")
    else:
        final = candidates[: cfg.top_k]
        for r in final:
            r.final_score = r.rrf_score

    return final
