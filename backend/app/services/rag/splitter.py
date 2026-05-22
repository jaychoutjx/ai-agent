"""
文本分块层。

【为什么要分块？面试必问】
1. Embedding 模型有最大 token 限制（如 text-embedding-v3 是 8192 tokens）
2. 大模型上下文窗口有限，不能把整本书塞进去
3. 分块越小，检索越精准；分块越大，上下文越完整 → 需要平衡
4. 常用大小：300-800 tokens，重叠 50-150 tokens

【为什么用 RecursiveCharacterTextSplitter？】
LangChain 的 RecursiveCharacterTextSplitter 是"递归"的：
- 优先按段落分（"\n\n"）
- 段落太长，按句子分（"。", "！", "？"）
- 句子太长，按逗号分
- 都不行才按字符硬切
这样能尽量保证语义完整，是面试默认答案。

【为什么要重叠（overlap）？】
避免"语义被切断"。比如一个完整的句子被分到两个块里，重叠能让两个块都包含这个句子。
"""

from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.logger import logger

CHINESE_SEPARATORS = [
    "\n\n",   # 段落
    "\n",     # 换行
    "。",     # 中文句号
    "！",
    "？",
    "；",
    ".",      # 英文句号
    "!",
    "?",
    ";",
    "，",     # 中文逗号（最后兜底）
    ",",
    " ",
    "",
]


def split_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
    metadata: dict | None = None,
) -> list[LCDocument]:
    """
    将长文本分块。

    Args:
        text: 待分块的文本
        chunk_size: 单块目标字符数（中文按字符算）
        chunk_overlap: 块之间的重叠字符数
        metadata: 注入到每个块的元数据（如 document_id、source）

    Returns:
        LangChain Document 对象列表，每个 Document 包含 page_content + metadata
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=CHINESE_SEPARATORS,
        keep_separator=True,
        is_separator_regex=False,
    )

    docs = splitter.create_documents([text], metadatas=[metadata or {}])
    logger.info(
        f"分块完成: {len(text)} 字符 → {len(docs)} 块 "
        f"(chunk_size={chunk_size}, overlap={chunk_overlap})"
    )
    return docs
