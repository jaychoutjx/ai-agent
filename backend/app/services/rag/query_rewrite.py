"""
Query 改写服务。

【为什么 Query 改写很重要？面试必讲】
用户的原始问题往往：
- 太短，缺乏关键词
- 用词跟文档不一致（比如用户问"咋办"，文档写"如何处理"）
- 太抽象，需要补充上下文

Query 改写的核心思想：让 LLM 先把用户问题"改写"成更适合检索的若干个查询，
然后用这些改写后的 query 一起检索，最后把结果合并去重。

【两种主流策略】

1. Multi-Query: 生成 N 个语义等价但不同表述的查询
   原: "RAG 是什么？"
   改: ["什么是检索增强生成？", "RAG 的工作原理是怎样的？", "为什么需要 RAG？"]

2. HyDE (Hypothetical Document Embedding): 让 LLM 先"幻想"一个答案，再用这个答案去检索
   原: "RAG 是什么？"
   幻: "RAG 是一种结合检索与生成的技术，先从知识库检索文档，再让模型基于检索结果生成回答..."
   再用这个"假设答案"做向量检索（因为答案和真实文档语义更接近）

实际效果：HyDE 在专业问答中通常比 Multi-Query 更好，但延迟更高。
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.logger import logger
from app.services.llm.chat_model import get_chat_model

MULTI_QUERY_PROMPT = """你是一个搜索查询改写助手。
用户给了一个问题，请生成 {n} 个语义等价但表述不同的搜索查询，用于知识库检索。

【要求】
- 保持原问题核心意图
- 每个改写查询独立成行，不要序号、不要解释
- 使用与文档可能匹配的关键词（比如同义词、专业术语）
- 不超过 30 字

【原问题】
{question}

【改写查询（每行一个，共 {n} 行）】"""


HYDE_PROMPT = """你是一个百科全书编辑。
请根据下面的问题，写出一段 100-200 字的回答（即使你不确定细节，也要写出合理的内容）。
这段回答只用于辅助检索，不会展示给用户，所以请尽量像维基百科条目一样客观陈述。

【问题】
{question}

【假设答案】"""


async def multi_query_rewrite(question: str, n: int = 3) -> list[str]:
    """
    Multi-Query：生成 N 个改写查询。

    Returns:
        包含原问题在内的查询列表（共 n+1 个）
    """
    if n <= 0:
        return [question]

    prompt = ChatPromptTemplate.from_messages([("human", MULTI_QUERY_PROMPT)])
    llm = get_chat_model(temperature=0.7, streaming=False, max_tokens=512)
    chain = prompt | llm | StrOutputParser()

    try:
        text = await chain.ainvoke({"question": question, "n": n})
        queries = [
            line.strip().lstrip("0123456789.、) ").strip()
            for line in text.splitlines()
            if line.strip()
        ]
        # 去重 + 去空 + 截断
        queries = list({q for q in queries if q})[:n]
        logger.info(f"Multi-Query 改写: {len(queries)} 个变体")
        return [question, *queries]
    except Exception as e:
        logger.warning(f"Multi-Query 改写失败，降级用原查询: {e}")
        return [question]


async def hyde_rewrite(question: str) -> str:
    """
    HyDE：让 LLM 先生成一个"假设答案"，用这个答案做检索。

    Returns:
        假设答案文本（拼上原问题，用于增强检索）
    """
    prompt = ChatPromptTemplate.from_messages([("human", HYDE_PROMPT)])
    llm = get_chat_model(temperature=0.5, streaming=False, max_tokens=512)
    chain = prompt | llm | StrOutputParser()

    try:
        hypothesis = await chain.ainvoke({"question": question})
        # 把原问题 + 假设答案拼起来检索（增强检索）
        result = f"{question}\n{hypothesis.strip()}"
        logger.info(f"HyDE 生成假设答案: {len(hypothesis)} 字符")
        return result
    except Exception as e:
        logger.warning(f"HyDE 改写失败，降级用原查询: {e}")
        return question
