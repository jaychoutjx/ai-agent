"""
文档管理 API。

端点：
- POST   /api/v1/documents/upload         上传 + 异步入库
- GET    /api/v1/documents                列出所有文档
- GET    /api/v1/documents/{id}           查询单个文档
- DELETE /api/v1/documents/{id}           删除文档（含分块）

【面试可讲】为什么用 BackgroundTasks 异步处理？
- 上传一份大 PDF 可能需要 10-30s（解析 + 向量化）
- HTTP 接口不能让用户等这么久
- 立即返回 202 Accepted，后台慢慢处理
- 前端轮询 GET /documents/{id} 查看状态
"""

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from app.core.config import settings
from app.core.logger import logger
from app.schemas.document import (
    DocumentListResponse,
    DocumentMeta,
    DocumentStatus,
    DocumentUploadResponse,
)
from app.services.rag.bm25 import get_bm25_retriever
from app.services.rag.ingestion import ingest_document
from app.services.rag.parser import SUPPORTED_EXTENSIONS
from app.services.rag.repository import get_document_repo
from app.services.rag.vector_store import delete_by_document

router = APIRouter()

UPLOAD_DIR = Path(settings.upload_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def _process_document(
    file_path: Path,
    document_id: str,
    document_name: str,
) -> None:
    """后台任务：解析 + 分块 + 向量化 + 入库，并更新文档状态。"""
    repo = get_document_repo()
    try:
        repo.update_status(document_id, DocumentStatus.PARSING)
        chunk_count = await ingest_document(
            file_path=file_path,
            document_id=document_id,
            document_name=document_name,
        )
        repo.update_status(
            document_id, DocumentStatus.READY, chunk_count=chunk_count
        )
        logger.info(f"文档处理完成: {document_name}, chunks={chunk_count}")
    except Exception as e:
        logger.exception(f"文档处理失败: {document_name}")
        repo.update_status(
            document_id, DocumentStatus.FAILED, error_message=str(e)
        )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    """上传文档并异步入库。"""
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            400,
            f"不支持的文件格式 {ext}，支持：{sorted(SUPPORTED_EXTENSIONS)}",
        )

    max_size = settings.max_upload_size_mb * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_size:
        raise HTTPException(
            413, f"文件过大，最大允许 {settings.max_upload_size_mb} MB"
        )

    document_id = uuid.uuid4().hex
    save_path = UPLOAD_DIR / f"{document_id}{ext}"
    save_path.write_bytes(contents)

    doc = DocumentMeta(
        id=document_id,
        filename=file.filename,
        file_type=ext.lstrip("."),
        file_size=len(contents),
        status=DocumentStatus.PENDING,
    )
    get_document_repo().add(doc)

    background_tasks.add_task(_process_document, save_path, document_id, file.filename)

    return DocumentUploadResponse(document=doc)


@router.get("", response_model=DocumentListResponse)
async def list_documents() -> DocumentListResponse:
    """列出所有文档。"""
    docs = get_document_repo().list_all()
    return DocumentListResponse(total=len(docs), documents=docs)


@router.get("/{doc_id}", response_model=DocumentMeta)
async def get_document(doc_id: str) -> DocumentMeta:
    """查询单个文档（前端轮询用）。"""
    doc = get_document_repo().get(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    return doc


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str) -> None:
    """删除文档（含 Milvus 中的所有分块和上传的源文件）。"""
    repo = get_document_repo()
    doc = repo.get(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")

    await delete_by_document(doc_id)
    get_bm25_retriever().invalidate()

    src = UPLOAD_DIR / f"{doc_id}.{doc.file_type}"
    if src.exists():
        src.unlink()

    repo.delete(doc_id)
    logger.info(f"删除文档: {doc.filename}")
