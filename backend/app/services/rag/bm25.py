"""
BM25 关键词检索器（中文友好版）。

【为什么需要 BM25？面试必讲】
向量检索（语义匹配）虽然好，但有它解决不了的问题：
1. 专有名词（比如人名、产品代号、错误码）—— 向量模型没见过会失效
2. 数字 / 缩写 / 代号（比如 "v3"、"GPT-4"、"HTTP 401"）
3. 完全相同的词形匹配（用户搜什么就要精准命中）

BM25 就是经典的"关键词 + 词频"算法，对上述场景特别有效。
混合检索（BM25 + 向量）能综合两者优势，是 RAG 高级检索的标配。

【中文优化】
英文 BM25 直接按空格分词即可，中文必须先分词。我们用 jieba（最常用的中文分词库）。

【从哪儿拿数据？】
BM25 是基于"全部分块"算 TF-IDF 的，必须把当前知识库的所有文本加载到内存。
我们从 Milvus 拉取所有分块（仅当前 Collection），构建 BM25 索引。
生产环境会用 Elasticsearch / OpenSearch 做这件事，我们这里用本地内存版。
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from functools import lru_cache

import jieba
from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.core.logger import logger
from app.services.rag.vector_store import COLLECTION_NAME, get_milvus_client

# 简单中英文混合分词正则（先用正则切英文/数字，剩下的中文交给 jieba）
_EN_TOKEN = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    """中英文混合分词，去掉停用词。"""
    if not text:
        return []
    text = text.lower()

    tokens: list[str] = []
    last_end = 0
    for m in _EN_TOKEN.finditer(text):
        # 英文/数字 token 之间的中文片段交给 jieba
        zh = text[last_end : m.start()]
        if zh.strip():
            tokens.extend(t for t in jieba.lcut(zh) if t.strip())
        tokens.append(m.group(0))
        last_end = m.end()
    # 末尾剩余中文
    zh = text[last_end:]
    if zh.strip():
        tokens.extend(t for t in jieba.lcut(zh) if t.strip())

    # 过滤掉单字符 / 全标点
    return [t for t in tokens if len(t) > 1 or _EN_TOKEN.match(t)]


@dataclass
class BM25Doc:
    """BM25 索引中的一条记录。"""

    chunk_id: str
    content: str
    document_id: str
    document_name: str
    chunk_index: int


class BM25Retriever:
    """
    内存版 BM25 检索器。

    生命周期：
    - 首次使用时从 Milvus 拉所有分块
    - 之后缓存（每次 add/delete 后需调用 invalidate() 重建）
    """

    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._docs: list[BM25Doc] = []
        self._lock = asyncio.Lock()

    async def _build_if_needed(self) -> None:
        """惰性构建索引。"""
        if self._bm25 is not None:
            return

        async with self._lock:
            if self._bm25 is not None:
                return

            client = get_milvus_client()
            # 拉取整个 collection（实际生产应分页）
            rows = await asyncio.to_thread(
                client.query,
                collection_name=COLLECTION_NAME,
                filter="",  # 空过滤 = 全部
                output_fields=[
                    "id",
                    "content",
                    "document_id",
                    "document_name",
                    "chunk_index",
                ],
                limit=10000,
            )
            self._docs = [
                BM25Doc(
                    chunk_id=str(r.get("id", "")),
                    content=str(r.get("content", "")),
                    document_id=str(r.get("document_id", "")),
                    document_name=str(r.get("document_name", "")),
                    chunk_index=int(r.get("chunk_index", 0)),
                )
                for r in rows
            ]

            if not self._docs:
                self._bm25 = None
                logger.warning("BM25 索引为空（Milvus 中暂无分块）")
                return

            corpus = [tokenize(d.content) for d in self._docs]
            self._bm25 = BM25Okapi(corpus)
            logger.info(f"BM25 索引构建完成: {len(self._docs)} 个分块")

    def invalidate(self) -> None:
        """让缓存失效。下次检索会重建。"""
        self._bm25 = None
        self._docs = []
        logger.info("BM25 索引已失效，下次检索将重建")

    async def search(
        self,
        query: str,
        top_k: int = 10,
        document_ids: list[str] | None = None,
    ) -> list[tuple[BM25Doc, float]]:
        """
        BM25 检索。

        Returns:
            [(BM25Doc, BM25 分数), ...] 按分数从高到低排序
        """
        await self._build_if_needed()
        if not self._bm25 or not self._docs:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        # 过滤 document_ids
        candidates: list[tuple[BM25Doc, float]] = []
        for doc, s in zip(self._docs, scores, strict=True):
            if document_ids and doc.document_id not in document_ids:
                continue
            candidates.append((doc, float(s)))

        # 按分数排序
        candidates.sort(key=lambda x: x[1], reverse=True)
        # 过滤掉 0 分（完全无关的）
        candidates = [c for c in candidates if c[1] > 0]
        return candidates[:top_k]


@lru_cache(maxsize=1)
def get_bm25_retriever() -> BM25Retriever:
    return BM25Retriever()


# 当 vector_store 入库/删除时，记得调用：
#     get_bm25_retriever().invalidate()
# 这里通过 monkey-patch 或者上层调用来触发；我们在 ingestion 里手动调
