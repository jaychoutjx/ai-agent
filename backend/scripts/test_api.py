"""
测试 FastAPI HTTP 接口（含 SSE 流式）。

需要先启动后端：
    uv run uvicorn app.main:app --port 8800
然后运行：
    uv run python scripts/test_api.py
"""

import asyncio
import json
import time

import httpx


API_BASE = "http://127.0.0.1:8800"


async def test_health():
    print("\n[Test 1] GET /api/v1/health")
    print("-" * 60)
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{API_BASE}/api/v1/health")
        print(f"Status: {r.status_code}")
        print(f"Body: {r.json()}")
        assert r.status_code == 200


async def test_chat_completions():
    print("\n[Test 2] POST /api/v1/chat/completions (非流式)")
    print("-" * 60)
    async with httpx.AsyncClient(timeout=60) as client:
        t0 = time.perf_counter()
        r = await client.post(
            f"{API_BASE}/api/v1/chat/completions",
            json={
                "message": "用一句话介绍 LangChain。",
                "history": [],
                "stream": False,
            },
        )
        elapsed = time.perf_counter() - t0
        print(f"Status: {r.status_code} | 耗时: {elapsed:.2f}s")
        data = r.json()
        print(f"模型: {data['model']}")
        print(f"回答: {data['content']}")
        assert r.status_code == 200


async def test_chat_stream():
    print("\n[Test 3] POST /api/v1/chat/completions/stream (SSE 流式)")
    print("-" * 60)

    async with httpx.AsyncClient(timeout=60) as client:
        t0 = time.perf_counter()
        first_token_time = None
        chunk_count = 0
        full_text = ""

        async with client.stream(
            "POST",
            f"{API_BASE}/api/v1/chat/completions/stream",
            json={
                "message": "用 2 句话讲讲 SSE 协议。",
                "history": [],
                "stream": True,
            },
            headers={"Accept": "text/event-stream"},
        ) as response:
            print(f"Status: {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type')}")
            print()
            print("流式输出: ", end="", flush=True)

            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                    if "content" in payload:
                        if first_token_time is None:
                            first_token_time = time.perf_counter() - t0
                        print(payload["content"], end="", flush=True)
                        full_text += payload["content"]
                        chunk_count += 1
                except json.JSONDecodeError:
                    continue

        total_time = time.perf_counter() - t0
        print()
        print(f"\n首 token 延迟 (TTFT): {first_token_time:.2f}s")
        print(f"总耗时: {total_time:.2f}s")
        print(f"chunk 数: {chunk_count}")
        print(f"总长度: {len(full_text)} 字符")
        print(f"输出速度: {len(full_text) / total_time:.1f} 字符/秒")


async def main():
    print("=" * 60)
    print("FastAPI HTTP 接口联调测试")
    print("=" * 60)
    try:
        await test_health()
        await test_chat_completions()
        await test_chat_stream()
        print("\n" + "=" * 60)
        print("✅ 所有 HTTP 接口测试通过！")
        print("=" * 60)
    except httpx.ConnectError:
        print("\n❌ 连不上后端，请确认 http://127.0.0.1:8800 已启动")
    except Exception as e:
        print(f"\n❌ 失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
