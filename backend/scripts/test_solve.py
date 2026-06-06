"""
拍照搜题端到端测试。

流程：
1. 用 PIL 现画一张清晰的题目图片（数学题），转成 base64 data URI
2. 调用 solve_question_stream（真实调用 Qwen-VL）
3. 打印流式解题过程，校验首 token 延迟、是否识别出题目、是否给出答案

运行方式（pillow 临时注入，不写入 pyproject）：
    uv run --with pillow python scripts/test_solve.py
"""

import asyncio
import base64
import io
import sys
import time
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 以便打印中文/emoji 的解题内容
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.services.solve.service import solve_question_stream


def make_question_image() -> str:
    """画一张数学题图片，返回 data URI。"""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 320), "white")
    draw = ImageDraw.Draw(img)

    # 尽量找一个能渲染中文的字体，找不到就用默认（英文/数字仍清晰）
    font = None
    for fp in [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, 40)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    lines = [
        "解方程：",
        "    x^2 - 5x + 6 = 0",
        "",
        "求 x 的所有实数解。",
    ]
    y = 40
    for line in lines:
        draw.text((50, y), line, fill="black", font=font)
        y += 60

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def mask(key: str) -> str:
    if not key or len(key) < 12:
        return "(empty)"
    return f"{key[:6]}...{key[-4:]}"


async def main() -> None:
    print("=" * 60)
    print("拍照搜题端到端测试（Qwen-VL）")
    print("=" * 60)
    print(f"Base URL : {settings.dashscope_base_url}")
    print(f"VL 模型  : {settings.qwen_vl_model}")
    print(f"API Key  : {mask(settings.dashscope_api_key)}")

    if not settings.dashscope_api_key or settings.dashscope_api_key.startswith("sk-your"):
        print("\n❌ 请先在 .env 中填写 DASHSCOPE_API_KEY")
        return

    print("\n[1] 生成题目图片：x^2 - 5x + 6 = 0")
    image_uri = make_question_image()
    print(f"    图片大小: {len(image_uri) // 1024} KB (base64)")

    print("\n[2] 调用 solve_question_stream（subject=math）流式解题：")
    print("-" * 60)
    t0 = time.perf_counter()
    first = None
    full = ""
    try:
        stream = await solve_question_stream(
            image_base64=image_uri,
            subject="math",
            extra=None,
        )
        async for chunk in stream:
            if first is None:
                first = time.perf_counter() - t0
            print(chunk, end="", flush=True)
            full += chunk
    except Exception as e:
        print(f"\n\n❌ 调用失败: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return

    total = time.perf_counter() - t0
    print("\n" + "-" * 60)
    print(f"首 token 延迟 (TTFT): {first:.2f}s" if first else "无输出")
    print(f"总耗时: {total:.2f}s | 输出字符数: {len(full)}")

    # 简单校验
    ok_answer = ("2" in full and "3" in full)  # 正确解 x=2, x=3
    ok_struct = ("答案" in full) or ("解题" in full)
    print("\n校验：")
    print(f"  {'✅' if ok_answer else '❌'} 识别并解出正确答案 (x=2, x=3)")
    print(f"  {'✅' if ok_struct else '❌'} 输出包含结构化解题内容")
    if ok_answer and ok_struct:
        print("\n🎉 端到端通过！拍照搜题链路正常。")
    else:
        print("\n⚠️ 链路跑通但结果不完全符合预期，请人工看上面输出。")


if __name__ == "__main__":
    asyncio.run(main())
