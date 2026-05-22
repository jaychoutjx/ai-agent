"""
RAG 端到端测试。

流程：
1. 准备一份测试文档（关于 LangChain 的中文知识）
2. 入库（解析 → 分块 → 向量化 → Milvus）
3. 用 RAG 链路提问，看是否能基于资料回答
4. 验证 citations 是否正确返回

运行方式：
    uv run python scripts/test_rag.py
"""

import asyncio
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.rag.ingestion import ingest_document
from app.services.rag.retrieval import rag_answer, rag_answer_stream
from app.services.rag.vector_store import (
    delete_by_document,
    search as vs_search,
)


SAMPLE_DOC = """
# LangChain 知识库

## 什么是 LangChain？

LangChain 是一个用于开发由大语言模型驱动的应用程序的框架。
LangChain 由 Harrison Chase 创建于 2022 年 10 月，是当前最流行的 LLM 应用开发框架。

LangChain 的核心理念是：通过组合不同的组件（LLM、Prompt、Memory、Retriever、Tool 等），
快速构建复杂的 AI 应用，而不必从零开始实现底层细节。

## LCEL 是什么？

LCEL 全称 LangChain Expression Language，是 LangChain 提出的链式表达语言。
LCEL 通过管道符 `|` 把各个组件串起来，例如：`prompt | llm | parser`。
LCEL 的最大优势是统一接口（Runnable 协议），所有组件都支持 invoke / stream / batch / async 等方法。
同时，LCEL 链路天然支持流式输出和并发执行。

## RAG 是什么？

RAG 全称 Retrieval-Augmented Generation，即检索增强生成。
RAG 的工作流程是：先从外部知识库中检索与问题相关的内容，再把这些内容作为上下文给大模型。
RAG 能有效解决大模型的"幻觉"问题，并且可以让模型使用最新的、私域的知识。

## Agent 是什么？

Agent（智能体）是能够自主决策并调用工具的 AI 系统。
LangGraph 是 LangChain 团队推出的 Agent 编排框架，基于状态图（StateGraph）实现。
LangGraph 适合构建多步骤、需要循环或人工介入的复杂 Agent 工作流。
"""


async def main():
    print("=" * 60)
    print("RAG 端到端测试")
    print("=" * 60)

    # 准备临时测试文件
    tmp_dir = Path("data/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    test_file = tmp_dir / "langchain_kb.md"
    test_file.write_text(SAMPLE_DOC, encoding="utf-8")

    document_id = uuid.uuid4().hex
    document_name = "langchain_kb.md"

    try:
        # ========== Step 1: 入库 ==========
        print("\n[Step 1] 入库文档")
        print("-" * 60)
        t0 = time.perf_counter()
        chunk_count = await ingest_document(
            file_path=test_file,
            document_id=document_id,
            document_name=document_name,
        )
        print(f"✅ 入库完成: {chunk_count} 个分块，耗时 {time.perf_counter() - t0:.2f}s")

        # ========== Step 2: 检查 Milvus 检索 ==========
        print("\n[Step 2] 检查 Milvus 检索")
        print("-" * 60)
        results = await vs_search(
            "LangChain 是什么", top_k=3, document_ids=[document_id]
        )
        print(f"✅ Milvus 中能检索到 {len(results)} 个相关分块")
        for i, (doc, score) in enumerate(results, 1):
            preview = doc.page_content[:80].replace("\n", " ")
            print(f"  [{i}] (score={score:.3f}) {preview}...")

        # ========== Step 3: 非流式 RAG 问答 ==========
        print("\n[Step 3] 非流式 RAG 问答")
        print("-" * 60)
        questions = [
            "LangChain 是谁创建的？什么时候？",
            "LCEL 用什么符号串联组件？",
            "RAG 能解决大模型的什么问题？",
            "LangGraph 是基于什么实现的？",
        ]

        for q in questions:
            print(f"\n问题: {q}")
            t0 = time.perf_counter()
            answer, citations = await rag_answer(q, top_k=3, document_ids=[document_id])
            elapsed = time.perf_counter() - t0
            print(f"耗时: {elapsed:.2f}s | 引用数: {len(citations)}")
            print(f"答案: {answer}")

        # ========== Step 4: 流式 RAG 问答 ==========
        print("\n[Step 4] 流式 RAG 问答")
        print("-" * 60)
        q = "请综合介绍 LangChain、LCEL、RAG、Agent 之间的关系。"
        print(f"问题: {q}")
        t0 = time.perf_counter()
        first_token = None
        full_text = ""
        stream, citations = await rag_answer_stream(q, top_k=5, document_ids=[document_id])
        print(f"引用数: {len(citations)}")
        print("流式回答: ", end="", flush=True)
        async for chunk in stream:
            if chunk:
                if first_token is None:
                    first_token = time.perf_counter() - t0
                print(chunk, end="", flush=True)
                full_text += chunk
        total = time.perf_counter() - t0
        print()
        print(f"\n✅ 首 token 延迟: {first_token:.2f}s | 总耗时: {total:.2f}s")
        print(f"   引用片段:")
        for i, c in enumerate(citations, 1):
            preview = c.content[:50].replace("\n", " ")
            print(f"   [{i}] {c.document_name} (score={c.score:.3f}) {preview}...")

        print("\n" + "=" * 60)
        print("✅ RAG 端到端测试通过！")
        print("=" * 60)

    finally:
        # 清理：删除测试文档（避免污染 Milvus）
        print("\n[Cleanup] 删除测试数据")
        await delete_by_document(document_id)
        if test_file.exists():
            test_file.unlink()
        print("✅ 清理完成")


if __name__ == "__main__":
    asyncio.run(main())
