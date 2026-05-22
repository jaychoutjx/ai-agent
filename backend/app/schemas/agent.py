"""Agent 相关的 Pydantic Schema。"""

from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    """Agent 问答请求。"""

    question: str = Field(..., min_length=1, max_length=4000)
    history: list[dict] = Field(default_factory=list, description="历史对话")
    document_ids: list[str] | None = Field(
        default=None, description="限定 RAG 检索的文档 ID；None 表示全库"
    )
    stream: bool = Field(default=True)
