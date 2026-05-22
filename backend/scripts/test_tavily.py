"""
单独测试 Tavily 联网搜索是否配通。

用法：
    1. 在 .env 里填好 TAVILY_API_KEY
    2. uv run python scripts/test_tavily.py

如果输出"✅ Tavily 联网搜索成功"，就说明 web_search 工具已经能用了。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.services.agent.tools import web_search


async def main():
    print("=" * 60)
    print("Tavily 联网搜索测试")
    print("=" * 60)

    if not settings.tavily_api_key:
        print("\n❌ 未检测到 TAVILY_API_KEY")
        print("请到 https://tavily.com 注册（免费），把 key 填到 .env 的 TAVILY_API_KEY")
        return

    print(f"\n✅ 检测到 TAVILY_API_KEY: {settings.tavily_api_key[:10]}...")

    queries = [
        "OpenAI 最近发布了什么模型",
        "2026 年最新的 LLM benchmark 排名",
        "LangChain 最新版本是多少",
    ]

    for q in queries:
        print(f"\n{'─' * 60}")
        print(f"问题: {q}")
        print("─" * 60)
        # web_search 是 LangChain @tool，调用方式：.ainvoke({"query": q})
        result = await web_search.ainvoke({"query": q})
        print(result[:600] + ("..." if len(result) > 600 else ""))

    print("\n" + "=" * 60)
    print("✅ Tavily 联网搜索测试通过")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
