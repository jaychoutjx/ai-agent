"""
Embedding 模型封装（阿里云百炼 text-embedding-v3）。

【为什么选 text-embedding-v3？】
1. Qwen 团队最新版，2025 年下半年发布，中文场景 SOTA
2. 1024 维（性价比甜点，比 1536/3072 更适合 Milvus 索引）
3. 与百炼平台无缝集成（同一个 Key，开发体验最佳）
4. 兼容 OpenAI 协议，直接用 langchain_openai.OpenAIEmbeddings 调用

【面试可讲的优化点】
- 批量调用：一次请求多条文本，降低调用次数（百炼支持单次最多 25 条）
- check_embedding_ctx_length=False：跳过本地 token 计数（百炼侧自己处理）
- 避免重复向量化：上层做缓存（按文本 hash）
"""

from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from app.core.config import settings
from app.core.logger import logger


@lru_cache(maxsize=1)
def get_embedding_model() -> OpenAIEmbeddings:
    """
    获取 Qwen Embedding 模型实例。

    DashScope 兼容 OpenAI 协议，所以复用 OpenAIEmbeddings 类。
    """
    if not settings.dashscope_api_key or settings.dashscope_api_key.startswith("sk-your"):
        logger.warning("⚠️  DashScope API Key 未配置，向量化将失败")

    logger.info(
        f"初始化 Embedding: model={settings.qwen_embedding_model}, "
        f"dim={settings.embedding_dim}"
    )

    return OpenAIEmbeddings(
        model=settings.qwen_embedding_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        dimensions=settings.embedding_dim,
        timeout=30,
        max_retries=3,
        # 百炼单次最多 25 条文本
        chunk_size=25,
        # 关闭本地 tiktoken 计数（百炼模型不在 tiktoken 词表中，会报错）
        check_embedding_ctx_length=False,
    )
