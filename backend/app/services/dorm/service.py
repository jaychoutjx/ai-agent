"""
寝室群聊三大能力服务层：
1. 检索问答（query）  - 基于 RAG，"我们上周谁说要去吃火锅"
2. 总结报告（summary）- 时间范围 + Map-Reduce 总结，"上周群聊重点 / 高频话题 / 大事记"
3. 人设模仿（imitate）- few-shot prompt 让 LLM 模仿某人风格回复

【面试可讲】这是一组在同一份语料上的多任务示范——
RAG 不只是"检索 + 生成"，**针对不同问题类型选择合适的链路**才是真功夫。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.core.logger import logger
from app.schemas.dorm import DormCitation
from app.services.dorm.parser import parse_iso_date
from app.services.dorm.vector_store import (
    query_by_time_range,
    search_sessions,
)
from app.services.llm.chat_model import get_chat_model

# ============================================================
# 1. 检索问答
# ============================================================

DORM_QUERY_SYSTEM = """你是一位"寝室群聊记忆助手"，帮助 {owner} 回忆和分析他们寝室群里发生过的事情。

【参考资料】是从他们 7 人寝室微信群「{group_name}」的聊天记录里检索出的相关片段，每段都有时间和参与者。

【回答风格】
- 用轻松、生活化的口吻（这是室友间的私密群聊，不需要正式）
- 适当 emoji，贴合大学生氛围 🤣
- 涉及具体事件务必引用时间 / 参与人，例如："9 月 12 日晚上你和高瑞祥讨论过去吃火锅"
- 如果资料不足以回答，**坦诚回答"群聊记录里我没找到相关线索，可能是发的图片/语音"**
- **不要**在文中插入 [1][2][3] 这种引用编号

【参考资料】
{context}
"""

DORM_QUERY_USER = "{question}"


def _format_dorm_context(citations: list[DormCitation]) -> str:
    """把检索到的会话块拼成 LLM 上下文。"""
    if not citations:
        return "（未检索到任何相关聊天记录）"
    blocks: list[str] = []
    for i, c in enumerate(citations, 1):
        members = "、".join(c.participants[:5])
        blocks.append(
            f"[片段 {i}] {c.start_time} ~ {c.end_time}（{members}）\n{c.content}"
        )
    return "\n\n---\n\n".join(blocks)


async def dorm_query_stream(
    question: str,
    top_k: int = 8,
    start_date: str | None = None,
    end_date: str | None = None,
    participants: list[str] | None = None,
    group_name: str = "寝室群",
) -> tuple[AsyncIterator[str], list[DormCitation]]:
    """
    寝室检索问答（流式）。

    Returns:
        (流式 chunk 异步迭代器, 引用片段列表)
    """
    start_ts = parse_iso_date(start_date)
    end_ts_base = parse_iso_date(end_date)
    # end_date 应该包含当天，所以加 86400-1
    end_ts = end_ts_base + 86399 if end_ts_base else None

    citations = await search_sessions(
        question,
        top_k=top_k,
        start_ts=start_ts,
        end_ts=end_ts,
        participants=participants,
    )

    if not citations:
        async def empty() -> AsyncIterator[str]:
            yield "群聊记录里我没找到相关线索 🤔，要不你换个关键词试试？"

        return empty(), []

    context = _format_dorm_context(citations)
    prompt = ChatPromptTemplate.from_messages(
        [("system", DORM_QUERY_SYSTEM), ("human", DORM_QUERY_USER)]
    )
    llm = get_chat_model(temperature=0.5, streaming=True)
    chain = prompt | llm | StrOutputParser()

    stream = chain.astream(
        {
            "question": question,
            "context": context,
            "owner": settings.dorm_owner_name,
            "group_name": group_name,
        }
    )
    return stream, citations


# ============================================================
# 2. 总结报告（Map-Reduce）
# ============================================================

DORM_SUMMARY_MAP_PROMPT = """以下是「{group_name}」寝室群一段时间内的部分聊天记录。
请提炼这段记录中的关键信息，输出 1-3 句话的小结，保留具体的人名和事件。

【聊天片段】
{chunk}

【小结】"""

DORM_SUMMARY_REDUCE_PROMPT = """你正在写一份「{group_name}」寝室群在 {range_label} 的群聊报告。
下面是若干段聊天记录的小结，请整理成一份完整的群聊周报，要求：

1. 用 Markdown 格式
2. 包含以下板块：
   - 📅 **时间范围** 与消息总数
   - 🔥 **本期热点话题**（3-5 条，每条一句话 + 涉及到的人）
   - 🎭 **本期金句 / 趣事**（2-3 条，能体现寝室氛围）
   - 👥 **本期发言情况**（谁最活跃 / 谁比较安静）
3. 风格轻松活泼，是写给寝室成员看的，不要正式商务腔
4. 不要凭空编造信息，所有事件都基于下面的小结
5. 不要在文中输出 [1][2] 这类引用编号

【小结集合】
{summaries}

【群聊报告】"""


async def dorm_summary(
    range_: str = "week",
    end_date: str | None = None,
    group_name: str = "寝室群",
) -> str:
    """
    生成寝室群聊周报 / 月报。

    Args:
        range_: "day" / "week" / "month" / "all"
        end_date: 截止日期 YYYY-MM-DD，默认 None=今天
    """
    # 计算时间范围
    end_dt = (
        datetime.strptime(end_date, "%Y-%m-%d")
        if end_date
        else datetime.now()
    )
    if range_ == "day":
        start_dt = end_dt - timedelta(days=1)
        range_label = f"{start_dt.strftime('%Y-%m-%d')}"
    elif range_ == "week":
        start_dt = end_dt - timedelta(days=7)
        range_label = f"近一周（{start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')}）"
    elif range_ == "month":
        start_dt = end_dt - timedelta(days=30)
        range_label = f"近一月（{start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')}）"
    else:
        # all：用一个不可能的过去时间
        start_dt = datetime(2000, 1, 1)
        range_label = "全部时间"

    start_ts = int(start_dt.timestamp())
    end_ts = int((end_dt + timedelta(days=1)).timestamp())  # 包含今天

    # 拉时间范围内所有会话块
    sessions = await query_by_time_range(start_ts, end_ts, limit=1500)
    if not sessions:
        return f"## {range_label} 群聊报告\n\n这段时间内群里没有聊天记录哦 😴"

    total_msgs = sum(int(s.get("msg_count", 0)) for s in sessions)
    logger.info(
        f"[dorm-summary] {range_label}: {len(sessions)} 块会话, {total_msgs} 条消息"
    )

    llm_fast = get_chat_model(model="qwen-turbo", temperature=0.3, streaming=False)
    llm_smart = get_chat_model(temperature=0.7, max_tokens=2500, streaming=False)

    # ---- Map：每个会话块单独总结（并发）----
    import asyncio as _asyncio

    map_prompt = ChatPromptTemplate.from_template(DORM_SUMMARY_MAP_PROMPT)
    map_chain = map_prompt | llm_fast | StrOutputParser()

    # 控制并发避免限流：每批 8 个
    BATCH = 8
    summaries: list[str] = []
    for i in range(0, len(sessions), BATCH):
        batch = sessions[i : i + BATCH]
        batch_results = await _asyncio.gather(
            *(
                map_chain.ainvoke(
                    {"group_name": group_name, "chunk": s.get("content", "")}
                )
                for s in batch
            )
        )
        summaries.extend(batch_results)
    logger.info(f"[dorm-summary] map 阶段完成: {len(summaries)} 个小结")

    # 截断 summaries 避免 reduce prompt 太长（保留前 80 个最有代表性的）
    if len(summaries) > 80:
        summaries = summaries[:80]

    summaries_block = "\n".join([f"- {s.strip()}" for s in summaries if s.strip()])

    # ---- Reduce：合成最终报告 ----
    reduce_prompt = ChatPromptTemplate.from_template(DORM_SUMMARY_REDUCE_PROMPT)
    reduce_chain = reduce_prompt | llm_smart | StrOutputParser()
    report = await reduce_chain.ainvoke(
        {
            "group_name": group_name,
            "range_label": range_label,
            "summaries": summaries_block,
        }
    )
    # 在报告头部加一行硬指标
    header = (
        f"> 📊 共 **{len(sessions)}** 个会话块、**{total_msgs}** 条消息（{range_label}）\n\n"
    )
    return header + report


# ============================================================
# 3. 人设模仿（few-shot）
# ============================================================

DORM_IMITATE_SYSTEM = """你正在模仿「{target}」的说话风格，回复别人对 TA 说的话。

【模仿要求】
- 严格基于下面【风格示例】里 {target} 在群里的真实发言
- 模仿用词、语气、长短、emoji 习惯
- 一句话回复就好，不要长篇大论
- 不要解释你在模仿，**直接以 {target} 的口吻回**
- 不要使用 [1] [2] 这种引用标号

【风格示例（{target} 在群里的发言）】
{examples}

请用 {target} 的风格，回复下面这句话："""


async def dorm_imitate(
    target_member: str,
    user_message: str,
) -> AsyncIterator[str]:
    """
    模仿某成员的说话风格回复（流式）。

    实现思路：
    1. 用 user_message 在该成员的发言里做向量检索（带 participants 过滤）
    2. 拿到 5-10 条该成员的真实发言
    3. 拼成 few-shot prompt 喂给 LLM
    """
    # 把 user_message 当 query 检索 target_member 的相关发言
    citations = await search_sessions(
        user_message,
        top_k=8,
        participants=[target_member],
    )

    examples_lines: list[str] = []
    for c in citations:
        # 从会话块里抽取 target_member 自己说的话
        for line in c.content.split("\n"):
            if f"] {target_member}:" in line:
                # 截取冒号后的发言
                idx = line.find(f"] {target_member}:")
                msg = line[idx + len(f"] {target_member}:") :].strip()
                if msg and len(msg) <= 120:
                    examples_lines.append(msg)

    # 去重 + 限长
    seen: set[str] = set()
    deduped: list[str] = []
    for m in examples_lines:
        if m not in seen:
            seen.add(m)
            deduped.append(m)
        if len(deduped) >= 12:
            break

    if not deduped:
        # 找不到该成员的发言时，给个礼貌的兜底
        async def fallback() -> AsyncIterator[str]:
            yield (
                f"咦，群里没找到「{target_member}」说过类似的话哎，"
                "TA 可能没怎么聊过这个话题 🤔"
            )

        return fallback()

    examples_block = "\n".join([f"- {m}" for m in deduped])

    prompt = ChatPromptTemplate.from_messages(
        [("system", DORM_IMITATE_SYSTEM), ("human", "{user_message}")]
    )
    llm = get_chat_model(temperature=0.9, max_tokens=200, streaming=True)
    chain = prompt | llm | StrOutputParser()
    return chain.astream(
        {
            "target": target_member,
            "examples": examples_block,
            "user_message": user_message,
        }
    )
