"""
Zilliz Cloud 连通性测试。

用法（PowerShell）：
    cd backend
    uv run python scripts/test_zilliz.py

测试内容：
    1. 能否连上 Zilliz Cloud
    2. Collection 是否能创建/加载
    3. 能否插入一条测试数据
    4. 能否检索回来
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 让脚本能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.logger import logger


def main() -> None:
    print("=" * 60)
    print("Zilliz Cloud 连通性测试")
    print("=" * 60)

    print(f"\n[配置检查]")
    print(f"  MILVUS_URI:   {settings.milvus_uri or '(未配置，将连本地 Milvus)'}")
    print(f"  MILVUS_TOKEN: {'(已配置)' if settings.milvus_token else '(未配置)'}")
    print(f"  COLLECTION:   {settings.milvus_collection}")

    if not settings.milvus_uri:
        print("\n❌ 错误：未配置 MILVUS_URI，请在 .env 中填入 Zilliz 的 endpoint")
        sys.exit(1)
    if not settings.milvus_token:
        print("\n❌ 错误：未配置 MILVUS_TOKEN")
        sys.exit(1)

    print("\n[Step 1] 尝试连接 Zilliz Cloud...")
    from app.services.rag.vector_store import get_milvus_client

    try:
        client = get_milvus_client()
        print(f"  ✅ 连接成功")
    except Exception as e:
        print(f"  ❌ 连接失败：{e}")
        print(f"\n  排查建议：")
        print(f"  - 检查 MILVUS_URI 是否完整（含 https://）")
        print(f"  - 检查 MILVUS_TOKEN 是否正确")
        print(f"  - 检查网络是否能访问 zillizcloud.com")
        sys.exit(1)

    print("\n[Step 2] 列出当前 Collections...")
    try:
        cols = client.list_collections()
        print(f"  ✅ 现有 Collections: {cols}")
    except Exception as e:
        print(f"  ❌ 列表失败：{e}")
        sys.exit(1)

    print("\n[Step 3] 测试插入 + 检索...")

    async def _embed_test():
        from app.services.llm.embedding import get_embedding_model

        em = get_embedding_model()
        vec = await em.aembed_query("Hello Zilliz Cloud")
        return vec

    try:
        vec = asyncio.run(_embed_test())
        print(f"  ✅ Embedding 维度: {len(vec)}")
    except Exception as e:
        print(f"  ❌ Embedding 失败：{e}")
        sys.exit(1)

    test_id = "zilliz_smoke_test_001"
    try:
        client.insert(
            collection_name=settings.milvus_collection,
            data=[{
                "id": test_id,
                "embedding": vec,
                "content": "Zilliz Cloud smoke test",
                "document_id": "smoke_test",
                "document_name": "smoke_test.txt",
                "chunk_index": 0,
            }],
        )
        print(f"  ✅ 插入测试数据成功 (id={test_id})")
    except Exception as e:
        print(f"  ❌ 插入失败：{e}")
        sys.exit(1)

    try:
        results = client.search(
            collection_name=settings.milvus_collection,
            data=[vec],
            anns_field="embedding",
            search_params={"metric_type": "COSINE", "params": {"ef": 64}},
            output_fields=["content"],
            limit=1,
        )
        print(f"  ✅ 检索成功，命中: {results[0][0].get('entity', {}).get('content')}")
    except Exception as e:
        print(f"  ❌ 检索失败：{e}")
        sys.exit(1)

    # 清理测试数据
    try:
        client.delete(
            collection_name=settings.milvus_collection,
            filter=f'id == "{test_id}"',
        )
        print(f"  ✅ 清理测试数据完成")
    except Exception as e:
        print(f"  ⚠️ 清理失败（不影响）：{e}")

    print("\n" + "=" * 60)
    print("🎉 全部通过！Zilliz Cloud 配置成功，可以部署到服务器了。")
    print("=" * 60)


if __name__ == "__main__":
    main()
