"""聊天相关的 Pydantic Schema。"""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    """聊天请求体。"""

    message: str = Field(..., min_length=1, max_length=8000, description="用户当前消息")
    history: list[ChatMessage] = Field(default_factory=list, description="历史对话")
    stream: bool = Field(default=True, description="是否流式返回")
    temperature: float = Field(default=0.7, ge=0, le=2)


class ChatResponse(BaseModel):
    """非流式响应。"""

    content: str
    model: str
