"""
全局配置中心。

- 使用 pydantic-settings，从 .env 文件读取配置
- 所有配置项类型安全，IDE 可补全
- 单例模式，整个应用共享一个 settings 实例
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR.parent / ".env"


class Settings(BaseSettings):
    """应用配置。字段名与 .env 中的 KEY 大小写无关地匹配。"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 应用 ----------
    app_name: str = "AI-Knowledge-Base"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8800

    # ---------- 阿里云百炼（DashScope）----------
    dashscope_api_key: str = Field(default="", description="阿里云百炼 API Key")
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # 各场景模型
    qwen_chat_model: str = "qwen-plus"
    qwen_reasoner_model: str = "qwq-plus"
    qwen_embedding_model: str = "text-embedding-v3"
    qwen_reranker_model: str = "gte-rerank-v2"

    embedding_dim: int = 1024

    # ---------- Milvus / Zilliz Cloud ----------
    # 本地 Milvus 模式：milvus_host + milvus_port
    # Zilliz Cloud 模式：milvus_uri + milvus_token（优先级高于 host/port）
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "aikb_knowledge"
    milvus_uri: str = ""    # Zilliz Cloud Endpoint（填了就走云端）
    milvus_token: str = ""  # Zilliz Cloud Token

    # ---------- PostgreSQL ----------
    database_url: str = "postgresql+asyncpg://aikb:aikb_dev_password@localhost:5432/aikb"

    # ---------- Redis ----------
    redis_url: str = "redis://localhost:6379/0"

    # ---------- Langfuse ----------
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # ---------- Tavily 联网搜索 ----------
    tavily_api_key: str = ""

    # ---------- 鉴权 ----------
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080

    # ---------- 文件上传 ----------
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50

    # ---------- CORS ----------
    cors_origins: str = "http://localhost:3000,http://localhost:3300,http://127.0.0.1:3300"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """单例 Settings。lru_cache 保证只创建一次。"""
    return Settings()


settings = get_settings()
