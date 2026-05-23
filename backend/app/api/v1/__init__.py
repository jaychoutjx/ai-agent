"""API v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import agent, chat, documents, dorm, health, rag

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(dorm.router, prefix="/dorm", tags=["dorm"])
