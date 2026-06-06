"""
拍照搜题（多模态解题）相关 Pydantic Schema。

【设计思路】
和"知识库 RAG"不同，搜题不依赖检索，而是直接把题目图片喂给多模态大模型
（Qwen-VL），让模型完成"识别题目 → 判断学科 → 作答 → 讲解步骤"一条龙。

为什么不做"OCR + 纯文本解题"两段式？
- 数学/物理/化学题大量含公式、图形、几何图，OCR 容易丢信息
- 多模态模型端到端理解图片，对图表/手写体更鲁棒，链路也更短
"""

from typing import Literal

from pydantic import BaseModel, Field

# 支持的学科（None / "auto" 表示让模型自动判断）
SubjectType = Literal[
    "auto", "math", "physics", "chemistry", "biology",
    "english", "chinese", "history", "geography", "politics", "other",
]


class SolveRequest(BaseModel):
    """拍照搜题请求。"""

    # 题目图片：data URI（"data:image/png;base64,xxxx"）或纯 base64
    image_base64: str = Field(
        ...,
        min_length=16,
        description="题目图片，data URI 或纯 base64 字符串",
    )
    # 学科：auto 表示自动判断
    subject: SubjectType = Field(default="auto", description="学科，auto=自动判断")
    # 额外文字提示（可选，如"只解第 2 题""用初中知识解答"）
    extra: str | None = Field(
        default=None,
        max_length=500,
        description="额外的文字补充/要求",
    )
    stream: bool = Field(default=True)
