"""
测试 Milvus 连接。

需要 Milvus 在 localhost:19530 运行。

运行方式：
    uv run python scripts/test_milvus.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymilvus import MilvusClient, connections, utility

from app.core.config import settings


def main():
    print("=" * 60)
    print("Milvus 连接测试")
    print("=" * 60)
    print(f"Host: {settings.milvus_host}:{settings.milvus_port}")

    try:
        connections.connect(
            alias="default",
            host=settings.milvus_host,
            port=str(settings.milvus_port),
        )
        print("\n✅ Milvus 连接成功")

        version = utility.get_server_version()
        print(f"Milvus 版本: {version}")

        client = MilvusClient(uri=f"http://{settings.milvus_host}:{settings.milvus_port}")
        collections = client.list_collections()
        print(f"现有 Collections: {collections}")

        target = settings.milvus_collection
        if target in collections:
            stats = client.get_collection_stats(target)
            print(f"\n目标 Collection '{target}' 已存在，row_count={stats.get('row_count', 0)}")
        else:
            print(f"\n目标 Collection '{target}' 不存在（首次运行正常）")

        print("\n" + "=" * 60)
        print("✅ Milvus 可用，可以开始 RAG 开发")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 连接失败: {type(e).__name__}: {e}")
        print("\n请检查：")
        print("  1. Milvus 容器是否运行: docker ps | findstr milvus")
        print(f"  2. 端口 {settings.milvus_port} 是否可访问")


if __name__ == "__main__":
    main()
