"""
对正在运行的后端发真实 HTTP 请求，验证前端实际调用的 /api/v1/solve/stream SSE 端点。

运行：uv run --with pillow python scripts/test_solve_http.py
（需先启动后端：uv run uvicorn app.main:app --port 8800）
"""

import asyncio
import base64
import io
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import httpx

URL = "http://127.0.0.1:8800/api/v1/solve/stream"


def make_image_data_uri() -> str:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 300), "white")
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 40)
    for i, t in enumerate(
        ["解方程：", "    x^2 - 5x + 6 = 0", "", "求 x 的所有实数解。"]
    ):
        d.text((50, 40 + i * 60), t, fill="black", font=f)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


async def main() -> None:
    print("=" * 60)
    print("HTTP 端到端测试：POST", URL)
    print("=" * 60)
    payload = {
        "image_base64": make_image_data_uri(),
        "subject": "math",
        "extra": None,
        "stream": True,
    }

    full = ""
    got_done = False
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", URL, json=payload) as resp:
            print("HTTP 状态:", resp.status_code)
            print("Content-Type:", resp.headers.get("content-type"))
            print("-" * 60)
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    got_done = True
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "content":
                    chunk = obj.get("content", "")
                    print(chunk, end="", flush=True)
                    full += chunk
                elif obj.get("type") == "error":
                    print("\n❌ 服务端错误:", obj.get("error"))

    print("\n" + "-" * 60)
    print(f"收到 [DONE]: {got_done} | 输出字符数: {len(full)}")
    ok = ("2" in full and "3" in full) and got_done
    print(f"{'✅ HTTP 端到端通过（识别题目并解出 x=2, x=3）' if ok else '⚠️ 结果异常，请看上面输出'}")


if __name__ == "__main__":
    asyncio.run(main())
