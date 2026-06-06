"""
拍照搜题服务层。

核心：把"题目图片 + 可选文字要求"组装成一条多模态消息，喂给 Qwen-VL，
流式产出"题目识别 → 答案 → 解题步骤"的 Markdown 文本。

【面试可讲】
- 端到端多模态：不做 OCR + 纯文本两段式，直接让 VLM 理解图片，链路短、对公式/图形鲁棒
- LCEL 多模态消息：HumanMessage.content 用 [{type:text}, {type:image_url}] 结构
- 强约束 Prompt：固定输出结构（识别/学科/答案/步骤），低温度保证解题准确性
- 流式输出：astream + SSE，前端打字机式呈现解题过程
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logger import logger
from app.services.llm.chat_model import get_vision_model

# 学科名映射（用于 prompt 里给模型一个明确的提示）
_SUBJECT_LABELS: dict[str, str] = {
    "auto": "（自动判断学科）",
    "math": "数学",
    "physics": "物理",
    "chemistry": "化学",
    "biology": "生物",
    "english": "英语",
    "chinese": "语文",
    "history": "历史",
    "geography": "地理",
    "politics": "政治",
    "other": "综合",
}

SOLVE_SYSTEM = """你是一位经验丰富的全科金牌解题老师，擅长数学、物理、化学、生物、英语、语文等各科目。
用户会上传一张题目图片，请你严格按下面的结构作答（用 Markdown）：

## 📝 题目识别
准确誊写图片中的题目原文（公式用文字/符号清楚表达，如 x^2、√、∫、≤）。如有多道题，逐题编号识别。

## 🏷️ 学科与题型
判断这道题属于哪个学科、什么题型（选择/填空/计算/证明/作文…）。

## ✅ 答案
给出最终答案（选择题给选项，计算题给结果）。如有多题，逐题给出。

## 🧩 解题步骤
分步骤讲清楚推理过程，做到不跳步、逻辑清晰。必要时点出考点和易错点。

【要求】
- 解题严谨准确，宁可多解释也不要跳步
- 数学公式一律用标准 LaTeX 书写，前端会用 KaTeX 渲染：
  · 行内公式用单个美元号包裹，例如 $x^2 - 5x + 6 = 0$
  · 独立成行的公式用双美元号包裹，例如 $$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$
  · 分数用 \\frac{}{}，根号用 \\sqrt{}，上下标用 ^ 和 _，不要写成纯文本的 x^2 / √ 这种
- 如果图片模糊看不清、或根本不是题目，请直接说明，不要编造题目
- 全程使用中文讲解（英语题的答案部分除外）"""


def _normalize_image_url(image_base64: str) -> str:
    """把前端传来的图片统一成 data URI 形式。

    前端可能传：
    - 完整 data URI： "data:image/png;base64,xxxx" → 原样使用
    - 纯 base64：     "xxxx"                        → 补一个通用前缀
    """
    s = image_base64.strip()
    if s.startswith("data:"):
        return s
    return f"data:image/jpeg;base64,{s}"


async def solve_question_stream(
    image_base64: str,
    subject: str = "auto",
    extra: str | None = None,
) -> AsyncIterator[str]:
    """
    拍照搜题（流式）。

    Args:
        image_base64: 题目图片（data URI 或纯 base64）
        subject: 学科，"auto" 表示自动判断
        extra: 额外文字要求（可选）

    Returns:
        流式 chunk 异步迭代器（Markdown 文本）
    """
    image_url = _normalize_image_url(image_base64)
    subject_label = _SUBJECT_LABELS.get(subject, "（自动判断学科）")

    # 组装多模态 human message：文字要求 + 图片
    text_parts = [f"这是一道{subject_label}题目，请帮我识别并解答。"]
    if extra and extra.strip():
        text_parts.append(f"额外要求：{extra.strip()}")

    human = HumanMessage(
        content=[
            {"type": "text", "text": "\n".join(text_parts)},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
    )

    llm = get_vision_model(temperature=0.2, max_tokens=2500, streaming=True)
    logger.info(f"[solve] 开始解题: subject={subject}, has_extra={bool(extra)}")

    async def gen() -> AsyncIterator[str]:
        async for chunk in llm.astream([SystemMessage(content=SOLVE_SYSTEM), human]):
            text = chunk.content
            if isinstance(text, str) and text:
                yield text
            elif isinstance(text, list):
                # 兼容部分 SDK 返回的分块结构
                for part in text:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        yield part["text"]

    return gen()
