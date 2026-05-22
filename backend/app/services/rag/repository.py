"""
文档元数据仓库（简化版：进程内字典 + JSON 持久化）。

【为什么先做内存版？】
- 第一阶段先把 RAG 链路打通，元数据存哪里不影响主流程
- 用 JSON 文件持久化，重启后还能看到上传过的文档
- 后续接入 PostgreSQL 时只要替换这个 Repository，业务代码不变（依赖倒置）

【面试可讲】这其实就是 Repository 模式。
"""

import json
from pathlib import Path
from threading import Lock

from app.schemas.document import DocumentMeta, DocumentStatus

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DOCUMENTS_FILE = DATA_DIR / "documents.json"


class DocumentRepository:
    """文档元数据仓库。线程安全的内存字典 + JSON 落盘。"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._docs: dict[str, DocumentMeta] = {}
        self._load()

    def _load(self) -> None:
        if DOCUMENTS_FILE.exists():
            try:
                data = json.loads(DOCUMENTS_FILE.read_text(encoding="utf-8"))
                for item in data:
                    doc = DocumentMeta.model_validate(item)
                    self._docs[doc.id] = doc
            except Exception:
                pass

    def _save(self) -> None:
        data = [doc.model_dump(mode="json") for doc in self._docs.values()]
        DOCUMENTS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(self, doc: DocumentMeta) -> None:
        with self._lock:
            self._docs[doc.id] = doc
            self._save()

    def get(self, doc_id: str) -> DocumentMeta | None:
        return self._docs.get(doc_id)

    def list_all(self) -> list[DocumentMeta]:
        return sorted(self._docs.values(), key=lambda d: d.created_at, reverse=True)

    def update_status(
        self,
        doc_id: str,
        status: DocumentStatus,
        chunk_count: int | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._lock:
            doc = self._docs.get(doc_id)
            if not doc:
                return
            doc.status = status
            if chunk_count is not None:
                doc.chunk_count = chunk_count
            if error_message is not None:
                doc.error_message = error_message
            self._save()

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            if doc_id in self._docs:
                del self._docs[doc_id]
                self._save()
                return True
            return False


_repo = DocumentRepository()


def get_document_repo() -> DocumentRepository:
    """获取全局文档仓库（单例）。"""
    return _repo
