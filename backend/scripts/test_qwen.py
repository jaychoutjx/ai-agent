"""
最小化测试脚本：验证阿里云百炼 Qwen API Key 是否可用。

包含：
- Test 1: 同步调用 Chat 模型
- Test 2: 流式调用 Chat 模型
- Test 3: 多轮对话历史
- Test 4: Embedding 向量化（验证 RAG 关键依赖）

运行方式：
    uv run python scripts/test_qwen.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.services.llm.chains import build_chat_chain
from app.services.llm.embedding import get_embedding_model


def mask(key: str) -> str:
    if not key or len(key) < 12:
        return "(empty)"
    return f"{key[:6]}...{key[-4:]}"


async def test_basic_invoke():
    print("\n[Test 1] 同步调用 ainvoke")
    print("-" * 60)
    chain = build_chat_chain()
    t0 = time.perf_counter()
    result = await chain.ainvoke(
        {"history": [], "input": "用一句话介绍你自己，不超过 30 字。"}
    )
    elapsed = time.perf_counter() - t0
    print(f"耗时: {elapsed:.2f}s")
    print(f"回答: {result}")


async def test_stream():
    print("\n[Test 2] 流式调用 astream")
    print("-" * 60)
    chain = build_chat_chain()
    t0 = time.perf_counter()
    first_token_time = None
    full_text = ""
    chunk_count = 0

    print("回答: ", end="", flush=True)
    async for chunk in chain.astream(
        {"history": [], "input": "请用 3 句话讲一下什么是 RAG。"}
    ):
        if first_token_time is None and chunk:
            first_token_time = time.perf_counter() - t0
        print(chunk, end="", flush=True)
        full_text += chunk
        chunk_count += 1

    total_time = time.perf_counter() - t0
    print()
    print(f"\n首 token 延迟 (TTFT): {first_token_time:.2f}s")
    print(f"总耗时: {total_time:.2f}s")
    print(f"chunk 数: {chunk_count}")
    print(f"输出速度: {len(full_text) / total_time:.1f} 字符/秒")


async def test_multi_turn():
    print("\n[Test 3] 多轮对话 history")
    print("-" * 60)
    from langchain_core.messages import AIMessage, HumanMessage

    chain = build_chat_chain()
    history = [
        HumanMessage(content="我叫小明，今年 25 岁。"),
        AIMessage(content="好的小明，很高兴认识你！"),
    ]
    result = await chain.ainvoke({"history": history, "input": "我叫什么名字？"})
    print(f"回答: {result}")
    assert "小明" in result, "❌ 多轮对话 history 未生效"
    print("✅ history 生效")


async def test_embedding():
    print("\n[Test 4] Embedding 向量化（RAG 关键依赖）")
    print("-" * 60)
    embed = get_embedding_model()
    texts = [
        "RAG 是检索增强生成技术",
        "LangChain 是大模型应用开发框架",
        "今天天气真好",
    ]
    t0 = time.perf_counter()
    vectors = await embed.aembed_documents(texts)
    elapsed = time.perf_counter() - t0
    print(f"耗时: {elapsed:.2f}s | 向量数: {len(vectors)} | 维度: {len(vectors[0])}")

    # 简单验证：相似句子的向量距离应小于不相关句子
    import math

    def cos_sim(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb)

    sim_01 = cos_sim(vectors[0], vectors[1])  # RAG vs LangChain（相关）
    sim_02 = cos_sim(vectors[0], vectors[2])  # RAG vs 天气（无关）
    print(f"  RAG ↔ LangChain 相似度: {sim_01:.4f}")
    print(f"  RAG ↔ 天气     相似度: {sim_02:.4f}")
    assert sim_01 > sim_02, "❌ 相似度异常"
    print("✅ Embedding 工作正常（相关文本相似度更高）")


async def main() -> None:
    print("=" * 60)
    print("阿里云百炼 Qwen + LangChain 联调测试")
    print("=" * 60)
    print(f"Base URL: {settings.dashscope_base_url}")
    print(f"Chat 模型: {settings.qwen_chat_model}")
    print(f"Embedding 模型: {settings.qwen_embedding_model}")
    print(f"API Key: {mask(settings.dashscope_api_key)}")

    if not settings.dashscope_api_key or settings.dashscope_api_key.startswith("sk-your"):
        print("\n❌ 请先在 .env 中填写 DASHSCOPE_API_KEY")
        return

    try:
        await test_basic_invoke()
        await test_stream()
        await test_multi_turn()
        await test_embedding()
        print("\n" + "=" * 60)
        print("✅ 全部通过！可以启动前后端联调，并开始 RAG 开发了。")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
