"""
RAG 检索 + 生成链路（LCEL 实现）。

【整体链路】
    用户问题
       │
       ↓ (Query 改写 + 混合检索 + Rerank)
    Top-K 相关分块
       │
       ↓ (拼接成 context)
    Prompt: "基于下面资料回答问题：{context}\n问题：{question}"
       │
       ↓ (Qwen 流式生成)
    回答 + 引用列表
"""

from collections.abc import AsyncIterator

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.schemas.document import Citation
from app.services.llm.chat_model import get_chat_model
from app.services.rag.advanced_retrieval import (
    RagConfig,
    RetrievalResult,
    advanced_retrieve,
)

RAG_SYSTEM_PROMPT = """你是一个严谨、专业的知识库问答助手。

【回答要求】
1. **必须**基于下方提供的「参考资料」回答问题
2. 如果资料中没有相关内容，**必须**坦诚回答"根据已有资料无法回答这个问题"，不要编造
3. 使用 Markdown 格式，回答简洁清晰、有条理
4. 如果资料涉及代码，使用代码块呈现
5. 直接给出回答的正文，**不要**在文中插入 `[1]`、`[2]`、`【1】` 之类的引用编号
   （前端会单独以"参考来源"卡片形式展示引用资料，无需在正文中重复标注）

【参考资料】
{context}
"""

RAG_USER_PROMPT = """问题：{question}

请基于上面的参考资料回答。"""


def _format_context(results: list[RetrievalResult]) -> str:
    """把检索到的分块格式化成 Prompt 中的 context 字符串。"""
    blocks: list[str] = []
    for i, r in enumerate(results, start=1):
        source = r.document_name or "未知文档"
        blocks.append(
            f"[{i}] 来源: {source} (相关度: {r.final_score:.3f})\n{r.content}"
        )
    return "\n\n---\n\n".join(blocks)


def _to_citations(results: list[RetrievalResult]) -> list[Citation]:
    """把检索结果转成给前端的 Citation 列表。"""
    return [
        Citation(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            document_name=r.document_name or "未知文档",
            content=r.content,
            score=r.final_score,
            chunk_index=r.chunk_index,
        )
        for r in results
    ]


def _default_config() -> RagConfig:
    """默认配置：开启 BM25 + Rerank（性价比最高的组合）。"""
    return RagConfig(
        top_k=5,
        candidate_k=20,
        use_bm25=True,
        use_rerank=True,
        use_multi_query=False,
        use_hyde=False,
    )


async def rag_answer_stream(
    question: str,
    top_k: int = 5,
    document_ids: list[str] | None = None,
    config: RagConfig | None = None,
) -> tuple[AsyncIterator[str], list[Citation]]:
    """
    RAG 流式问答。

    Returns:
        (流式 chunk 异步迭代器, 引用列表)
    """
    cfg = config or _default_config()
    cfg.top_k = top_k

    results = await advanced_retrieve(question, config=cfg, document_ids=document_ids)

    if not results:
        async def empty_stream() -> AsyncIterator[str]:
            yield "根据已有资料无法回答这个问题（知识库中暂无相关内容）。"

        return empty_stream(), []

    context = _format_context(results)
    citations = _to_citations(results)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", RAG_SYSTEM_PROMPT),
            ("human", RAG_USER_PROMPT),
        ]
    )
    llm = get_chat_model(temperature=0.2, streaming=True)
    chain = prompt | llm | StrOutputParser()

    stream = chain.astream({"context": context, "question": question})
    return stream, citations


async def rag_answer(
    question: str,
    top_k: int = 5,
    document_ids: list[str] | None = None,
    config: RagConfig | None = None,
) -> tuple[str, list[Citation]]:
    """非流式版本。便于测试和调试。"""
    cfg = config or _default_config()
    cfg.top_k = top_k

    results = await advanced_retrieve(question, config=cfg, document_ids=document_ids)

    if not results:
        return ("根据已有资料无法回答这个问题（知识库中暂无相关内容）。", [])

    context = _format_context(results)
    citations = _to_citations(results)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", RAG_SYSTEM_PROMPT),
            ("human", RAG_USER_PROMPT),
        ]
    )
    llm = get_chat_model(temperature=0.2, streaming=False)
    chain = prompt | llm | StrOutputParser()
    answer = await chain.ainvoke({"context": context, "question": question})
    return answer, citations
