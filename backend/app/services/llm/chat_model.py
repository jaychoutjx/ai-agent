"""
阿里云百炼（DashScope）大模型封装。

【为什么选阿里云百炼？】
1. 一个 Key 通吃 Qwen 全系列 + Embedding + Reranker，省心
2. 国内访问稳定，延迟低
3. 完全兼容 OpenAI 协议（dashscope-compatible-mode），所以可直接复用 langchain-openai
4. 价格透明，企业开票方便（生产场景必备）
5. Qwen 系列模型在中文场景的能力业界领先

【模型选型对照表】
- qwen-turbo  : 速度最快，成本最低，适合简单分类/路由
- qwen-plus   : 性价比首选，适合大部分对话/问答场景（默认）
- qwen-max    : 能力最强，适合复杂推理/长文本
- qwq-plus    : 深度思考模型（类似 R1），自动产出 reasoning_content
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import logger


@lru_cache(maxsize=8)
def get_chat_model(
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    streaming: bool = True,
) -> ChatOpenAI:
    """
    获取 Qwen Chat 模型。

    Args:
        model: 模型名，None 则用 settings.qwen_chat_model（默认 qwen-plus）
        temperature: 温度系数，0=最确定，1=最随机
                     - 问答 / RAG 推荐 0.1-0.3（更精准）
                     - 闲聊 / 创意 0.7-1.0
        max_tokens: 单次回复最大 token 数
        streaming: 是否启用流式输出（前端打字机效果必须开）

    Returns:
        可用于 LCEL 链路的 ChatOpenAI 实例
    """
    if not settings.dashscope_api_key or settings.dashscope_api_key.startswith("sk-your"):
        logger.warning("⚠️  DashScope API Key 未配置，请到 .env 中填写 DASHSCOPE_API_KEY")

    model_name = model or settings.qwen_chat_model

    logger.info(
        f"初始化 ChatModel: model={model_name}, "
        f"temperature={temperature}, streaming={streaming}"
    )

    return ChatOpenAI(
        model=model_name,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        timeout=60,
        max_retries=3,
    )


@lru_cache(maxsize=2)
def get_reasoner_model(streaming: bool = True) -> ChatOpenAI:
    """
    获取深度推理模型（QwQ-Plus / Qwen 推理版）。

    适用场景：
    - 复杂数学/逻辑推理
    - 多步骤问题分解
    - Agent 中的 planner 节点

    注意：推理模型不支持 temperature/top_p 等参数（官方限制）。
    """
    logger.info(f"初始化 ReasonerModel: model={settings.qwen_reasoner_model}")

    return ChatOpenAI(
        model=settings.qwen_reasoner_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        streaming=streaming,
        timeout=120,
        max_retries=3,
    )
