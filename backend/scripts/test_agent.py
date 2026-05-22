"""
Agent 端到端测试。

测试场景：
1. 直接问答（不调工具）：测 LLM 能正确判断"不需要工具"
2. 计算器：测 calculator 工具
3. 当前时间：测 get_current_time 工具
4. 多步组合：先时间，再计算
5. RAG 检索（如果知识库有数据）

运行方式：
    uv run python scripts/test_agent.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.agent.graph import run_agent_stream


async def run_one(question: str, label: str):
    print(f"\n{'=' * 70}")
    print(f"[{label}] 问题: {question}")
    print(f"{'=' * 70}")
    t0 = time.perf_counter()

    final_text = ""
    citations_count = 0
    tool_calls: list[dict] = []
    step_count = 0

    async for ev in run_agent_stream(question=question):
        kind = ev.get("type")
        if kind == "step":
            step_count += 1
            print(f"[step {step_count}] → {ev['node']}")
        elif kind == "tool_call":
            print(f"  🔧 调用工具: {ev['tool_name']}({ev['arguments']})")
            tool_calls.append(ev)
        elif kind == "tool_result":
            preview = ev["summary"][:80].replace("\n", " ")
            print(f"  ↪ 结果: {preview}...")
        elif kind == "content":
            print(ev["content"], end="", flush=True)
            final_text += ev["content"]
        elif kind == "citations":
            citations_count = len(ev["citations"])
        elif kind == "done":
            break

    elapsed = time.perf_counter() - t0
    print(
        f"\n[完成] 耗时 {elapsed:.2f}s | "
        f"调用工具 {len(tool_calls)} 次 | "
        f"引用 {citations_count} 个 | "
        f"答案长度 {len(final_text)} 字符"
    )


async def main():
    print("=" * 70)
    print("LangGraph Agent 端到端测试")
    print("=" * 70)

    # 1. 简单问答（不需要工具）
    await run_one("你好，介绍一下你自己。", "Test 1: 简单问答")

    # 2. 当前时间
    await run_one("现在是几月几号？星期几？", "Test 2: 当前时间")

    # 3. 数学计算
    await run_one("(123 + 456) * 789 等于多少？", "Test 3: 计算器")

    # 4. 多步组合
    await run_one(
        "现在是几点？如果再过 3 小时 25 分钟是几点？请帮我算一下。",
        "Test 4: 多步组合（时间 + 计算）",
    )

    # 5. 知识库检索（如果库里没数据，会返回"未找到"，Agent 应该说没找到）
    await run_one(
        "我的知识库里有什么内容？总结一下。",
        "Test 5: 知识库检索",
    )

    print("\n" + "=" * 70)
    print("✅ Agent 全部测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
