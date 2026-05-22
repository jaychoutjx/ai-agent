"""
Reranker 重排服务（阿里云百炼 gte-rerank-v2）。

【为什么需要 Reranker？面试必讲】
向量检索 + BM25 都是 "Bi-Encoder" 范式：把 query 和 doc 分别编码成向量再算相似度。
这种方式速度快但精度有限：因为 query 和 doc 是独立编码，没看到对方。

Reranker 是 "Cross-Encoder"：把 query 和 doc 拼成一个序列输入模型，输出一个相关度分数。
这种方式精度高得多（论文证明召回 Top-100 后用 Reranker 重排，Recall@5 能从 70% → 90%+）
但速度慢，所以业界标准做法是：

    向量/BM25 召回 Top-50 (粗排) → Reranker 重排 → Top-5 (精排) → 给 LLM

【为什么用 gte-rerank-v2？】
- 阿里达摩院出品，中文场景效果好
- 直接走百炼平台，复用 DASHSCOPE_API_KEY，无需额外注册
- 原生支持中英文混合
"""

import asyncio
from functools import lru_cache

import httpx

from app.core.config import settings
from app.core.logger import logger

RERANK_API_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
)


class Reranker:
    """阿里云百炼 Reranker 客户端。"""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30)

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[tuple[int, float]]:
        """
        重排 documents，返回 [(原始索引, 相关度分数), ...] 按分数降序。

        Args:
            query: 用户问题
            documents: 待重排的文本列表（一般是粗排的 Top-50）
            top_n: 返回前 N 个；None 表示返回全部

        Returns:
            [(原始位置索引, 相关度分数), ...] 例如 [(3, 0.92), (1, 0.85), ...]
            调用方根据原始索引取回完整数据
        """
        if not documents:
            return []
        if top_n is None:
            top_n = len(documents)

        payload = {
            "model": settings.qwen_reranker_model,
            "input": {"query": query, "documents": documents},
            "parameters": {
                "return_documents": False,
                "top_n": top_n,
            },
        }
        headers = {
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

        try:
            res = await self._client.post(
                RERANK_API_URL, json=payload, headers=headers
            )
            res.raise_for_status()
            data = res.json()
        except httpx.HTTPError as e:
            logger.error(f"Reranker 调用失败: {e}")
            # 降级：保持原顺序，返回全 0.5 分
            return [(i, 0.5) for i in range(min(top_n, len(documents)))]

        results = data.get("output", {}).get("results", [])
        ranked: list[tuple[int, float]] = [
            (int(r["index"]), float(r["relevance_score"])) for r in results
        ]
        logger.info(
            f"Reranker 完成: query={query[:30]}..., {len(documents)} → top_{top_n}"
        )
        return ranked


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return Reranker()
