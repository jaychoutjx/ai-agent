"""
微信群聊 JSON 解析与会话聚合。

【为什么不能直接拿单条消息做 embedding？】
群聊文本平均长度只有 8 字，"哈哈"、"嗯"、"我"这种短消息：
1. embedding 后语义高度相似，互相干扰检索结果
2. 单看一条信息也无法回答任何"上下文型"问题

【解决方案：时间窗口 + 数量上限的会话聚合】
- 相邻两条消息时间差 < gap_minutes（默认 30 min）→ 同一个会话
- 单个会话块内消息数达到 max_msgs_per_chunk（默认 30）→ 强制切分
- 每个会话块作为 RAG 的最小检索单元

【面试可讲】这是典型的"领域定制化预处理"——
RAG 不是拿原始数据扔进去就行，**预处理质量决定上限**。
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.core.logger import logger
from app.schemas.dorm import DormMessage, DormSession

# 跳过的消息类型：表情/图片/系统消息等没有可索引文本
_SKIP_TYPES = {
    "动画表情",
    "图片消息",
    "视频消息",
    "语音消息",
    "系统消息",
    "链接消息",
    "转账消息",
    "文件消息",
    "小程序消息",
    "聊天记录",
    "位置消息",
    "名片消息",
    "群公告",
    "其他消息",
}


def _clean_content(text: str) -> str:
    """清洗消息文本：去掉首尾空白 + 无意义换行。"""
    if not text:
        return ""
    # 微信导出的 content 经常以 "\n" 开头
    return text.strip()


def _is_meaningful(text: str) -> bool:
    """过滤掉纯表情包、纯标点等没意义的内容。"""
    if not text:
        return False
    # 只剩 [xxx] 这种表情/系统占位
    if re.fullmatch(r"\[[^\]]+\]", text):
        return False
    # 纯标点 / 空白
    if re.fullmatch(r"[\s\W_]+", text):
        return False
    return True


def parse_wx_json(json_path: str | Path) -> tuple[dict, list[DormMessage]]:
    """
    解析微信导出的群聊 JSON。

    Returns:
        (session_meta, messages)
        session_meta: 群信息（nickname/messageCount/...）
        messages:     有意义的文本消息列表（已过滤）
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"微信 JSON 文件不存在: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    session_meta = data.get("session", {})
    raw_messages = data.get("messages", [])

    messages: list[DormMessage] = []
    for m in raw_messages:
        msg_type = m.get("type", "")
        if msg_type in _SKIP_TYPES:
            continue
        content = _clean_content(m.get("content", ""))
        if not _is_meaningful(content):
            continue

        sender = m.get("senderDisplayName") or "（未知）"
        # 群本身偶尔也会发系统通知，跳过
        if sender == session_meta.get("nickname"):
            continue

        messages.append(
            DormMessage(
                local_id=int(m.get("localId", 0)),
                create_time=int(m.get("createTime", 0)),
                formatted_time=str(m.get("formattedTime", "")),
                type=msg_type,
                content=content,
                sender=sender,
                is_send=bool(m.get("isSend", 0)),
            )
        )

    logger.info(
        f"解析完成: 群 '{session_meta.get('nickname', '?')}' "
        f"原始 {len(raw_messages)} 条 → 有效 {len(messages)} 条"
    )
    return session_meta, messages


def aggregate_sessions(
    messages: list[DormMessage],
    gap_minutes: int | None = None,
    max_msgs_per_chunk: int | None = None,
) -> list[DormSession]:
    """
    把消息流按时间窗口聚合成会话块（chunk）。

    规则：
    - 相邻消息间隔 > gap_minutes 时切块
    - 当前块消息数达到 max_msgs_per_chunk 时强制切块

    每块最终格式：
        [HH:MM] 张三: 我们今天去吃火锅吧
        [HH:MM] 李四: 好啊几点？
        [HH:MM] 张三: 七点
        ...
    """
    gap = (gap_minutes or settings.dorm_session_gap_minutes) * 60
    cap = max_msgs_per_chunk or settings.dorm_max_msgs_per_chunk

    if not messages:
        return []

    sessions: list[DormSession] = []
    bucket: list[DormMessage] = []

    def flush() -> None:
        if not bucket:
            return
        first = bucket[0]
        last = bucket[-1]
        participants = sorted({m.sender for m in bucket})
        # 同一天内只保留时间，跨天显示完整日期
        same_day = first.formatted_time[:10] == last.formatted_time[:10]
        date_prefix = first.formatted_time[:10]
        lines: list[str] = []
        if same_day:
            lines.append(f"日期: {date_prefix}")
            for m in bucket:
                hhmm = m.formatted_time[11:16]
                lines.append(f"[{hhmm}] {m.sender}: {m.content}")
        else:
            for m in bucket:
                lines.append(f"[{m.formatted_time}] {m.sender}: {m.content}")
        content = "\n".join(lines)

        sessions.append(
            DormSession(
                session_id=str(uuid.uuid4()),
                start_time=first.formatted_time,
                end_time=last.formatted_time,
                start_ts=first.create_time,
                end_ts=last.create_time,
                participants=participants,
                msg_count=len(bucket),
                content=content,
            )
        )

    prev_ts = None
    for m in messages:
        # 时间间隔判定
        if prev_ts is not None and (m.create_time - prev_ts) > gap:
            flush()
            bucket = []
        bucket.append(m)
        prev_ts = m.create_time
        # 数量上限判定
        if len(bucket) >= cap:
            flush()
            bucket = []
            prev_ts = None

    flush()
    logger.info(
        f"会话聚合: {len(messages)} 条消息 → {len(sessions)} 个会话块 "
        f"(gap={gap // 60}min, cap={cap})"
    )
    return sessions


def get_member_stats(messages: list[DormMessage]) -> list[dict]:
    """统计每个成员的发言情况，给前端展示。"""
    stats: dict[str, dict] = {}
    for m in messages:
        s = stats.setdefault(
            m.sender, {"name": m.sender, "message_count": 0, "total_chars": 0}
        )
        s["message_count"] += 1
        s["total_chars"] += len(m.content)

    out = []
    for s in stats.values():
        out.append(
            {
                "name": s["name"],
                "message_count": s["message_count"],
                "avg_length": (
                    round(s["total_chars"] / s["message_count"], 1)
                    if s["message_count"]
                    else 0
                ),
            }
        )
    out.sort(key=lambda x: x["message_count"], reverse=True)
    return out


def get_time_range(messages: list[DormMessage]) -> dict:
    """获取数据集时间范围。"""
    if not messages:
        return {"start": None, "end": None}
    return {
        "start": messages[0].formatted_time,
        "end": messages[-1].formatted_time,
    }


def parse_iso_date(s: str | None) -> int | None:
    """把 'YYYY-MM-DD' 转成 Unix 时间戳（当天 0 点）；非法/None 返回 None。"""
    if not s:
        return None
    try:
        return int(datetime.strptime(s, "%Y-%m-%d").timestamp())
    except ValueError:
        return None
