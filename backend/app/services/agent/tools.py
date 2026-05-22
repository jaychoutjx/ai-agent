"""
Agent 可调用的工具集。

【设计原则】
1. 用 LangChain 的 @tool 装饰器，自动生成 Function Calling 的 schema
2. 每个工具职责单一，名称和描述清晰（LLM 通过描述决定调用哪个工具）
3. 错误隔离：工具内部捕获异常，返回友好错误，不让 Agent 崩溃

【工具列表】
- search_knowledge_base: 在私有知识库（Milvus）中检索
- web_search:            联网搜索（暂用 mock，生产可接 Bing/Tavily）
- calculator:            数学计算（用 Python eval 安全沙箱）
- get_current_time:      获取当前日期时间
"""

from __future__ import annotations

import asyncio
import datetime
import operator as op
from functools import lru_cache
from typing import Any

from langchain_core.tools import tool

from app.core.config import settings
from app.core.logger import logger
from app.services.rag.advanced_retrieval import RagConfig, advanced_retrieve

# 模块级状态，存放本次 Agent 调用的"会话级别"参数
# （用一个简单的全局字典而不是 contextvar，简化第一版实现）
_call_context: dict[str, Any] = {}


def set_call_context(**kwargs) -> None:
    """在 Agent 启动前设置当前调用的上下文（如 selected_doc_ids）。"""
    _call_context.clear()
    _call_context.update(kwargs)


def get_call_context() -> dict[str, Any]:
    return _call_context


# ============================================================
# Tool 1: 知识库检索
# ============================================================
@tool
async def search_knowledge_base(query: str) -> str:
    """
    在企业内部知识库中检索相关信息。
    适用场景：回答关于上传文档内容的问题，比如"这份合同的违约条款是什么"、
    "我们的产品规格是什么"、"文档里提到了哪些技术"。
    输入：要检索的查询文本（建议用中文，10-50 字最佳）
    """
    document_ids = _call_context.get("selected_doc_ids")
    config = RagConfig(top_k=5, use_bm25=True, use_rerank=True)
    results = await advanced_retrieve(
        question=query, config=config, document_ids=document_ids
    )

    if not results:
        return "知识库中未找到相关内容。"

    # 把检索结果存到 call_context，让 Synthesizer 可以拿到引用
    citations = _call_context.setdefault("collected_citations", [])
    citations.extend(results)

    # 给 LLM 看的格式化摘要
    blocks = []
    for i, r in enumerate(results, 1):
        blocks.append(
            f"[资料{i}] {r.document_name} (相关度 {r.final_score:.2f})\n{r.content}"
        )
    return "\n\n".join(blocks)


# ============================================================
# Tool 2: 联网搜索（Tavily，专为 LLM 设计的搜索 API）
# ============================================================

@lru_cache(maxsize=1)
def _get_tavily_client():
    """
    懒加载 Tavily 客户端。
    没配置 key 时返回 None，工具会降级到 mock 模式。
    """
    api_key = settings.tavily_api_key
    if not api_key:
        return None
    try:
        from tavily import TavilyClient
        return TavilyClient(api_key=api_key)
    except Exception as e:
        logger.error(f"Tavily 客户端初始化失败: {e}")
        return None


def _format_tavily_results(data: dict) -> str:
    """
    把 Tavily 返回结构格式化成给 LLM 的 Markdown 文本。

    Tavily 返回包括：
    - answer:  AI 生成的总结（include_answer=True 时）
    - results: [{title, url, content, score, ...}, ...]
    """
    parts: list[str] = []

    answer = data.get("answer")
    if answer:
        parts.append(f"## 搜索摘要\n{answer}")

    results = data.get("results") or []
    if results:
        parts.append("## 检索结果")
        for i, r in enumerate(results, 1):
            title = r.get("title", "无标题")
            url = r.get("url", "")
            content = r.get("content", "").strip()
            if len(content) > 400:
                content = content[:400] + "..."
            parts.append(f"[{i}] **{title}**\n来源: {url}\n{content}")

    if not parts:
        return "联网搜索未返回任何结果。"
    return "\n\n".join(parts)


@tool
async def web_search(query: str) -> str:
    """
    联网搜索最新信息。
    适用场景：回答关于实时新闻、最新版本、当前价格、热门话题等知识库中没有的问题。
    比如"今天的股市行情"、"最新的 GPT 模型版本"、"OpenAI 最近发布了什么"。
    输入：搜索关键词（建议英文或中文都可，10-30 字最佳）
    """
    client = _get_tavily_client()

    # 没配置 key → 降级到 mock，不让 Agent 崩溃
    if client is None:
        await asyncio.sleep(0.3)
        logger.warning(
            f"[web_search] Tavily 未配置 API Key，使用 mock 模式: {query}"
        )
        return (
            f"（联网搜索功能未启用：未配置 TAVILY_API_KEY）\n"
            f"提示：请到 https://tavily.com 注册免费 key 后填入 .env 的 TAVILY_API_KEY。\n"
            f"用户搜索的查询是「{query}」，请基于你已有的知识谨慎回答，"
            f"并提醒用户结果可能不是最新的。"
        )

    try:
        # tavily-python 的 search() 是同步阻塞，丢到线程池执行
        data = await asyncio.to_thread(
            client.search,
            query=query,
            search_depth="basic",       # basic 比 advanced 快、便宜
            max_results=5,              # 5 条够 LLM 综合
            include_answer=True,        # 让 Tavily 给 AI 生成的总结
            include_raw_content=False,  # 不要原始 HTML，省 token
        )
        logger.info(
            f"[web_search] Tavily query='{query[:30]}', "
            f"得 {len(data.get('results') or [])} 条结果"
        )
        return _format_tavily_results(data)
    except Exception as e:
        logger.exception(f"[web_search] Tavily 调用失败: {e}")
        return (
            f"联网搜索失败：{type(e).__name__}: {e}\n"
            f"请基于已有知识谨慎回答，并提醒用户搜索遇到了问题。"
        )


# ============================================================
# Tool 3: 计算器（安全沙箱）
# ============================================================
SAFE_OPS = {
    "+": op.add,
    "-": op.sub,
    "*": op.mul,
    "/": op.truediv,
    "**": op.pow,
    "%": op.mod,
}


@tool
def calculator(expression: str) -> str:
    """
    数学计算器。支持加减乘除、幂运算、括号、小数。
    适用场景：用户问的问题需要精确计算（LLM 自己算容易出错）。
    比如 "（123 + 456）* 789"、"2 的 10 次方是多少"、"100 万的 5% 是多少"。
    输入：标准的数学表达式字符串，例如 "1 + 2 * 3" 或 "(100 + 200) * 0.05"
    """
    # 用 eval 但限制 builtins，只允许数字和运算符
    try:
        # 先做基础校验：只能包含数字、运算符、括号、小数点、空格
        allowed = set("0123456789+-*/(). %")
        for ch in expression:
            if ch not in allowed:
                return f"表达式包含非法字符 '{ch}'，只允许数字、+ - * / ( ) . %"

        result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
        return f"计算结果：{expression} = {result}"
    except Exception as e:
        return f"计算失败：{type(e).__name__}: {e}"


# ============================================================
# Tool 4: 当前时间
# ============================================================
@tool
def get_current_time() -> str:
    """
    获取当前的日期和时间。
    适用场景：用户问与"今天"、"现在"、"当前"相关的问题，
    比如"今天是几月几号"、"现在几点"、"今年是哪一年"。
    无输入参数。
    """
    now = datetime.datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return now.strftime(
        f"%Y年%m月%d日 {weekdays[now.weekday()]} %H时%M分"
    )


# ============================================================
# 工具注册表
# ============================================================
ALL_TOOLS = [search_knowledge_base, web_search, calculator, get_current_time]

TOOL_MAP = {t.name: t for t in ALL_TOOLS}
