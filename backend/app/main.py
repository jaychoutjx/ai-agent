"""
FastAPI 应用入口。

启动方式：
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import settings
from app.core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理。

    启动时：初始化数据库连接、Milvus 连接、Redis 连接等
    关闭时：优雅释放资源
    """
    logger.info(f"🚀 {settings.app_name} 启动中... env={settings.app_env}")
    logger.info(f"📚 API 文档: http://{settings.app_host}:{settings.app_port}/docs")

    yield

    logger.info("👋 应用关闭，清理资源...")


def create_app() -> FastAPI:
    """工厂函数：创建并配置 FastAPI 实例。"""
    app = FastAPI(
        title=settings.app_name,
        description="企业级智能知识库问答系统 - 基于 LangChain + LangGraph + 阿里云百炼 Qwen",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/")
    async def root():
        return JSONResponse(
            {
                "name": settings.app_name,
                "version": "0.1.0",
                "docs": "/docs",
                "health": "/api/v1/health",
            }
        )

    return app


app = create_app()
