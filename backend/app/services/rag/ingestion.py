"""
入库编排服务。

把文档变成 Milvus 中的向量，整个流程：
    文件路径 → 解析（parser）→ 分块（splitter）→ 入库（vector_store）

【面试可讲】这个层为什么单独抽出来？
- 单一职责：parser/splitter/vector_store 各管一摊
- 易于扩展：新增分块策略或者预处理只改这里
- 可观测：每一步都打日志，方便定位问题
"""

import uuid
from pathlib import Path

from app.core.logger import logger
from app.services.rag.bm25 import get_bm25_retriever
from app.services.rag.parser import parse_document
from app.services.rag.splitter import split_text
from app.services.rag.vector_store import add_chunks


async def ingest_document(
    file_path: str | Path,
    document_id: str,
    document_name: str,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> int:
    """
    入库一份文档。

    Args:
        file_path: 文档本地路径
        document_id: 文档 ID（外部传入，UUID）
        document_name: 文档原始文件名
        chunk_size: 分块大小
        chunk_overlap: 重叠

    Returns:
        分块数量
    """
    logger.info(f"开始入库: doc_id={document_id}, name={document_name}")

    # 1. 解析
    text = parse_document(file_path)
    if not text.strip():
        raise ValueError("文档解析后内容为空")

    # 2. 分块
    metadata = {
        "document_id": document_id,
        "document_name": document_name,
    }
    chunks = split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap, metadata=metadata)

    # 给每个 chunk 注入 chunk_index 元数据
    for idx, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = idx

    # 3. 生成稳定 ID 并入库
    ids = [f"{document_id}_{i}_{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
    await add_chunks(chunks, ids)

    # 4. BM25 索引失效（下次检索会重建）
    get_bm25_retriever().invalidate()

    logger.info(f"入库完成: doc_id={document_id}, 分块数={len(chunks)}")
    return len(chunks)
