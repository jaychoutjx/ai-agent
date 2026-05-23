"""分析微信群聊导出 JSON 的统计信息（数据探查用）。"""

import json
import sys
from collections import Counter
from pathlib import Path


def main(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    msgs = data["messages"]
    session = data["session"]

    print("=" * 60)
    print(f"群名: {session['nickname']}")
    print(f"消息总数: {len(msgs)}")
    print(f"时间范围: {msgs[0]['formattedTime']} ~ {msgs[-1]['formattedTime']}")
    print("=" * 60)

    print("\n【消息类型分布】")
    for t, c in Counter(m["type"] for m in msgs).most_common():
        print(f"  {t:12s}  {c:>6}  ({c * 100 / len(msgs):.1f}%)")

    print("\n【群成员】")
    for n, c in Counter(m["senderDisplayName"] for m in msgs).most_common(20):
        # senderDisplayName 可能是 None 或 "" → 显示成"（未知）"
        name = n if n else "（未知）"
        print(f"  {name:30s}  {c} 条")

    text_ms = [m for m in msgs if m["type"] == "文本消息"]
    text_lens = [len(m.get("content", "")) for m in text_ms]
    if text_lens:
        text_lens_sorted = sorted(text_lens)
        avg = sum(text_lens) / len(text_lens)
        med = text_lens_sorted[len(text_lens) // 2]
        p90 = text_lens_sorted[int(len(text_lens) * 0.9)]
        print("\n【文本消息长度】")
        print(f"  数量: {len(text_ms)}")
        print(f"  平均: {avg:.1f}, 中位数: {med}, P90: {p90}, 最大: {max(text_lens)}")

    print("\n【最近 10 条文本消息】")
    for m in text_ms[-10:]:
        content = m.get("content", "").replace("\n", " ").strip()
        if len(content) > 60:
            content = content[:60] + "..."
        sender = m.get("senderDisplayName") or "（未知）"
        print(f"  [{m['formattedTime']}] {sender}: {content}")

    print("\n【最早 5 条文本消息】")
    for m in text_ms[:5]:
        content = m.get("content", "").replace("\n", " ").strip()
        if len(content) > 60:
            content = content[:60] + "..."
        sender = m.get("senderDisplayName") or "（未知）"
        print(f"  [{m['formattedTime']}] {sender}: {content}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else r"C:\wx-rag\data\群聊_六个大鸟呲精说.json"
    if not Path(path).exists():
        print(f"文件不存在: {path}")
        sys.exit(1)
    main(path)
