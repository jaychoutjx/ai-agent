"""
寝室群聊 RAG 相关 Pydantic Schema。

【数据建模思路】
和"知识库"模式不同，寝室群聊数据有几个特点：
1. 每条消息很短（中位数 6 字），单条没有语义价值，必须按时间窗口聚合
2. 元数据丰富：发送者、时间、消息类型，都对检索/总结有用
3. 索引粒度是"会话块"（一段连续的对话），不是单条消息

所以我们引入 ChatSession 概念：
    一个 ChatSession = N 条紧邻的消息（gap 内 / 上限 N 条）
    会话块作为 RAG 的 chunk 入库
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ============================================================
# 数据导入相关
# ============================================================

class DormMessage(BaseModel):
    """单条消息（解析自微信 JSON 后）。"""

    local_id: int
    create_time: int  # Unix 时间戳
    formatted_time: str  # "2024-09-03 15:06:04"
    type: str  # "文本消息" / "引用消息" / ...
    content: str
    sender: str  # senderDisplayName，如 "高瑞祥（好儿）"
    is_send: bool  # 是不是 owner 自己发的


class DormSession(BaseModel):
    """一个会话块（连续 N 条消息聚合而成，作为 RAG 的检索单元）。"""

    session_id: str  # UUID
    start_time: str  # 第一条消息的时间
    end_time: str  # 最后一条消息的时间
    start_ts: int  # 起始 Unix 时间戳（用于时间范围筛选）
    end_ts: int
    participants: list[str]  # 参与者去重列表
    msg_count: int
    content: str  # 会话块的纯文本（"[14:23] 张三: 哈哈\n[14:24] 李四: 笑死"）


# ============================================================
# 接口请求 / 响应
# ============================================================

class DormQueryRequest(BaseModel):
    """寝室问答请求。"""

    question: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=8, ge=1, le=20)
    # 可选：限定时间范围（前端可能加日期选择器）
    start_date: str | None = Field(default=None, description="起始日期 YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="结束日期 YYYY-MM-DD")
    # 可选：限定参与者
    participants: list[str] | None = Field(default=None)
    history: list[dict] = Field(default_factory=list)
    stream: bool = Field(default=True)


class DormCitation(BaseModel):
    """寝室检索命中的引用片段（用于前端展示来源会话）。"""

    session_id: str
    start_time: str
    end_time: str
    participants: list[str]
    content: str
    score: float


class DormSummaryRequest(BaseModel):
    """寝室总结报告请求。"""

    range: Literal["day", "week", "month", "all"] = Field(
        default="week", description="总结时间范围"
    )
    end_date: str | None = Field(
        default=None,
        description="结束日期（YYYY-MM-DD），为空表示数据集中最近的日期",
    )


class DormImitateRequest(BaseModel):
    """人设模仿请求。"""

    target_member: str = Field(
        ..., description="模仿对象的昵称，必须是群成员之一"
    )
    user_message: str = Field(
        ..., min_length=1, max_length=500, description="向 TA 说的话"
    )
    stream: bool = Field(default=True)


class DormStatsResponse(BaseModel):
    """寝室数据集统计信息。"""

    total_sessions: int
    total_messages: int
    members: list[dict]  # [{name, message_count, avg_length}, ...]
    time_range: dict  # {start, end}
    indexed_at: datetime | None = None
