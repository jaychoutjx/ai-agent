"""
RAG 评估脚本：对比 5 种配置的效果。

【配置矩阵】
  Baseline:      只用向量检索（基础版）
  +BM25:         向量 + BM25 混合检索
  +Rerank:       向量 + BM25 + Reranker 重排
  +MultiQuery:   向量 + BM25 + Reranker + Multi-Query
  +HyDE:         向量 + BM25 + Reranker + HyDE

【评估指标】
- Recall@K: 命中的查询占比（关键词匹配是否在 Top-K 中）
- MRR:      正确分块的平均倒数排名

运行方式：
    uv run python scripts/eval_rag.py
"""

import asyncio
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval_data import EVAL_DOCUMENT, EVAL_QUESTIONS  # type: ignore

from app.services.rag.advanced_retrieval import RagConfig, advanced_retrieve
from app.services.rag.bm25 import get_bm25_retriever
from app.services.rag.ingestion import ingest_document
from app.services.rag.vector_store import delete_by_document


@dataclass
class EvalResult:
    name: str
    recall_at_5: float
    mrr: float
    avg_latency: float


def hit_rank(content: str, expected_keywords: list[str]) -> bool:
    """判断内容是否包含期望关键词中的至少一个。"""
    return any(kw.lower() in content.lower() for kw in expected_keywords)


async def eval_one_config(name: str, config: RagConfig, doc_id: str) -> EvalResult:
    """跑一组配置，返回评估指标。"""
    print(f"\n[{name}] 配置: {config}")
    hits = 0
    reciprocal_ranks: list[float] = []
    latencies: list[float] = []

    for q in EVAL_QUESTIONS:
        question = q["question"]
        expected = q["expected_keywords"]

        t0 = time.perf_counter()
        results = await advanced_retrieve(
            question, config=config, document_ids=[doc_id]
        )
        elapsed = time.perf_counter() - t0
        latencies.append(elapsed)

        # 找正确分块的排名（1-indexed）
        rank: int | None = None
        for i, r in enumerate(results, start=1):
            if hit_rank(r.content, expected):
                rank = i
                break

        if rank is not None and rank <= 5:
            hits += 1
            reciprocal_ranks.append(1.0 / rank)
            status = f"✅ rank={rank}"
        else:
            reciprocal_ranks.append(0.0)
            status = "❌ miss"
        print(f"  {status} | {question[:30]}... ({elapsed:.2f}s)")

    n = len(EVAL_QUESTIONS)
    recall = hits / n
    mrr = sum(reciprocal_ranks) / n
    avg_lat = sum(latencies) / len(latencies)

    return EvalResult(
        name=name,
        recall_at_5=recall,
        mrr=mrr,
        avg_latency=avg_lat,
    )


async def main():
    print("=" * 70)
    print("RAG 高级优化评估")
    print(f"评估文档: {len(EVAL_DOCUMENT)} 字符")
    print(f"评估问题: {len(EVAL_QUESTIONS)} 个")
    print("=" * 70)

    # === 准备：入库评估文档 ===
    print("\n[Setup] 入库评估文档...")
    tmp_dir = Path("data/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    test_file = tmp_dir / "eval_doc.md"
    test_file.write_text(EVAL_DOCUMENT, encoding="utf-8")
    doc_id = uuid.uuid4().hex
    chunk_count = await ingest_document(
        file_path=test_file,
        document_id=doc_id,
        document_name="eval_doc.md",
    )
    # 确保 BM25 缓存重建
    get_bm25_retriever().invalidate()
    print(f"✅ 入库完成: {chunk_count} 个分块")

    # 等 Milvus 数据可见
    await asyncio.sleep(1.5)

    try:
        configs = [
            ("Baseline (Vector)", RagConfig(use_bm25=False, use_rerank=False)),
            ("+ BM25 (Hybrid)", RagConfig(use_bm25=True, use_rerank=False)),
            ("+ Rerank", RagConfig(use_bm25=True, use_rerank=True)),
            (
                "+ MultiQuery",
                RagConfig(
                    use_bm25=True,
                    use_rerank=True,
                    use_multi_query=True,
                    multi_query_n=2,
                ),
            ),
            (
                "+ HyDE",
                RagConfig(
                    use_bm25=True,
                    use_rerank=True,
                    use_hyde=True,
                ),
            ),
        ]

        results: list[EvalResult] = []
        for name, cfg in configs:
            r = await eval_one_config(name, cfg, doc_id)
            results.append(r)

        # === 汇总报告 ===
        print("\n" + "=" * 70)
        print("评估结果汇总")
        print("=" * 70)
        print(f"\n{'配置':<22} {'Recall@5':>10} {'MRR':>10} {'平均延迟':>12}")
        print("-" * 60)
        baseline_recall = results[0].recall_at_5
        for r in results:
            delta = (
                f"(+{(r.recall_at_5 - baseline_recall) * 100:.1f}%)"
                if r.recall_at_5 > baseline_recall
                else ""
            )
            print(
                f"{r.name:<22} {r.recall_at_5:>9.1%}  {r.mrr:>9.3f}  {r.avg_latency * 1000:>9.0f}ms  {delta}"
            )

        print("\n" + "=" * 70)
        print("✅ 评估完成")
        print("=" * 70)

    finally:
        print("\n[Cleanup] 清理评估数据...")
        await delete_by_document(doc_id)
        get_bm25_retriever().invalidate()
        if test_file.exists():
            test_file.unlink()
        print("✅ 完成")


if __name__ == "__main__":
    asyncio.run(main())
