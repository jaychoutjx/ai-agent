"""
重置 Milvus Collection（删掉重建）。

适用场景：
- collection schema 改了
- 之前残留了无索引的脏 collection
- 想清空所有向量数据

运行方式：
    uv run python scripts/reset_milvus.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymilvus import MilvusClient

from app.core.config import settings
from app.services.rag.vector_store import _ensure_collection


def main():
    uri = f"http://{settings.milvus_host}:{settings.milvus_port}"
    client = MilvusClient(uri=uri)

    name = settings.milvus_collection
    if client.has_collection(name):
        print(f"删除 Collection: {name}")
        client.drop_collection(name)
    else:
        print(f"Collection 不存在: {name}")

    print(f"重新创建 Collection（含索引）...")
    _ensure_collection(client)
    print(f"✅ 完成: {name}")


if __name__ == "__main__":
    main()
