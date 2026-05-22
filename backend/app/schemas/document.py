"""
文档与分块相关的 Pydantic Schema。

【数据模型设计要点】
- Document: 一份原始文档（一个 PDF/Word 文件）
- Chunk:    文档分块后的片段（一份 PDF 通常会被切成几十到几千个 chunk）
- Citation: 检索命中的引用信息（提供给前端展示来源）

【面试可讲】为什么文档和分块要分开建模？
1. 一对多关系：1 个文档对应 N 个分块
2. 删除时级联：删除文档时要级联删除所有分块
3. 元数据复用：分块继承文档的元数据（来源、作者等）
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """文档处理状态机。"""

    PENDING = "pending"        # 已上传，等待处理
    PARSING = "parsing"        # 正在解析
    CHUNKING = "chunking"      # 正在分块
    EMBEDDING = "embedding"    # 正在向量化
    READY = "ready"            # 入库完成，可被检索
    FAILED = "failed"          # 处理失败


class DocumentMeta(BaseModel):
    """文档基础元数据。"""

    id: str = Field(..., description="文档 ID（UUID）")
    filename: str = Field(..., description="原始文件名")
    file_type: str = Field(..., description="文件扩展名，如 pdf/docx/md")
    file_size: int = Field(..., description="文件大小（字节）")
    chunk_count: int = Field(default=0, description="分块数量")
    status: DocumentStatus = Field(default=DocumentStatus.PENDING)
    error_message: str | None = Field(default=None, description="处理失败时的错误信息")
    created_at: datetime = Field(default_factory=datetime.now)


class Chunk(BaseModel):
    """一个文档分块。这是被向量化和存入 Milvus 的最小单位。"""

    id: str = Field(..., description="分块 ID（UUID）")
    document_id: str = Field(..., description="所属文档 ID")
    content: str = Field(..., description="分块文本内容")
    chunk_index: int = Field(..., description="在原文档中的序号（从 0 开始）")
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加元数据")


class Citation(BaseModel):
    """检索命中的引用信息（用于前端展示来源）。"""

    chunk_id: str
    document_id: str
    document_name: str = Field(..., description="文档原始文件名")
    content: str = Field(..., description="命中的文本片段")
    score: float = Field(..., description="相关度分数（0-1，越高越相关）")
    chunk_index: int = Field(..., description="在原文档中的位置")


class DocumentUploadResponse(BaseModel):
    """文档上传接口响应。"""

    document: DocumentMeta
    message: str = "上传成功，正在后台处理"


class DocumentListResponse(BaseModel):
    """文档列表响应。"""

    total: int
    documents: list[DocumentMeta]


class RagQueryRequest(BaseModel):
    """RAG 问答请求。"""

    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20, description="召回片段数")
    document_ids: list[str] | None = Field(
        default=None, description="限定检索范围；None 表示全库检索"
    )
    history: list[dict] = Field(default_factory=list, description="历史对话")
    stream: bool = Field(default=True)

    # ===== 高级检索开关 =====
    use_bm25: bool = Field(default=True, description="开启 BM25 混合检索")
    use_rerank: bool = Field(default=True, description="开启 Reranker 重排")
    use_multi_query: bool = Field(default=False, description="开启 Multi-Query 改写")
    use_hyde: bool = Field(default=False, description="开启 HyDE 假设文档嵌入")


class RagQueryResponse(BaseModel):
    """RAG 问答非流式响应。"""

    answer: str
    citations: list[Citation]
    model: str
