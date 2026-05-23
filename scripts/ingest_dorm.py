"""
寝室群聊数据一次性导入脚本。

用法（在 project-01 根目录）：
    # 1) 默认路径（C:\\wx-rag\\data 下唯一的 JSON）
    python scripts/ingest_dorm.py

    # 2) 指定文件
    python scripts/ingest_dorm.py --file "C:/wx-rag/data/群聊_xxx.json"

    # 3) 重新导入（先清库再灌）
    python scripts/ingest_dorm.py --reset

输出：
    - 解析消息数 / 跳过消息数
    - 聚合会话块数
    - 入库进度（每 200 块一次日志）
    - 总耗时 + 大致 token 消耗估算
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# 添加 backend 到 sys.path（让脚本能 import app.*）
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.logger import logger  # noqa: E402
from app.services.dorm.parser import (  # noqa: E402
    aggregate_sessions,
    get_member_stats,
    get_time_range,
    parse_wx_json,
)
from app.services.dorm.vector_store import (  # noqa: E402
    add_sessions,
    count_sessions,
    drop_collection,
)


def _find_default_file() -> str | None:
    """默认在 C:/wx-rag/data 找第一个 .json。"""
    p = Path("C:/wx-rag/data")
    if not p.exists():
        return None
    files = list(p.glob("*.json"))
    return str(files[0]) if files else None


async def main() -> None:
    ap = argparse.ArgumentParser(description="导入微信群聊到寝室向量库")
    ap.add_argument("--file", help="微信群聊 JSON 路径")
    ap.add_argument(
        "--reset",
        action="store_true",
        help="先删除现有 collection 再重新导入",
    )
    ap.add_argument(
        "--gap",
        type=int,
        default=settings.dorm_session_gap_minutes,
        help=f"会话切分时间窗口（分钟，默认 {settings.dorm_session_gap_minutes}）",
    )
    ap.add_argument(
        "--cap",
        type=int,
        default=settings.dorm_max_msgs_per_chunk,
        help=f"单个会话块最多消息数（默认 {settings.dorm_max_msgs_per_chunk}）",
    )
    args = ap.parse_args()

    # ===== 1. 找文件 =====
    file_path = args.file or _find_default_file()
    if not file_path:
        logger.error(
            "未找到微信 JSON 文件。请用 --file 指定，或把 JSON 放到 C:/wx-rag/data/"
        )
        sys.exit(1)
    logger.info(f"输入文件: {file_path}")

    t0 = time.time()

    # ===== 2. 解析 + 过滤 =====
    session_meta, messages = parse_wx_json(file_path)
    if not messages:
        logger.error("没有解析到任何有效文本消息，退出。")
        sys.exit(1)

    members = get_member_stats(messages)
    time_range = get_time_range(messages)
    logger.info(f"群名: {session_meta.get('nickname', '?')}")
    logger.info(f"时间范围: {time_range['start']} ~ {time_range['end']}")
    logger.info("成员发言统计:")
    for m in members:
        logger.info(
            f"  - {m['name']}: {m['message_count']} 条 (avg {m['avg_length']} 字)"
        )

    # ===== 3. 聚合会话块 =====
    sessions = aggregate_sessions(
        messages, gap_minutes=args.gap, max_msgs_per_chunk=args.cap
    )
    if not sessions:
        logger.error("聚合后没有会话块，退出。")
        sys.exit(1)

    avg_msgs = sum(s.msg_count for s in sessions) / len(sessions)
    avg_chars = sum(len(s.content) for s in sessions) / len(sessions)
    logger.info(
        f"会话块: {len(sessions)} 个，平均每块 {avg_msgs:.1f} 条消息 / {avg_chars:.0f} 字"
    )

    # 大致 token 估算：1 字 ≈ 1 token，每千 token 约 ¥0.0007
    total_chars = sum(len(s.content) for s in sessions)
    est_cost = total_chars / 1000 * 0.0007
    logger.info(
        f"预估 embedding 成本: ~¥{est_cost:.3f}（约 {total_chars} 字符 / token）"
    )

    # ===== 4. 重置 / 检查现有数据 =====
    if args.reset:
        logger.warning("--reset 启用：将删除现有 collection")
        await drop_collection()
    else:
        existing = await count_sessions()
        if existing > 0:
            logger.warning(
                f"collection 已有 {existing} 块数据。"
                "如需重置，请加 --reset；现在将以追加方式继续。"
            )

    # ===== 5. 入库 =====
    logger.info("开始 embedding + 入库...")
    await add_sessions(sessions)

    final_count = await count_sessions()
    dt = time.time() - t0
    logger.info("=" * 60)
    logger.info(f"✅ 导入完成！collection 当前共 {final_count} 块")
    logger.info(f"⏱️  耗时: {dt:.1f} 秒")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
