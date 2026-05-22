# 04 · RAG 模块

> 这是项目的核心。从"用户传一个 PDF"到"得到带引用的回答"，每一步怎么做。

---

## 一、模块全景

```
backend/app/services/rag/
├── parser.py              # 文档解析（PDF/DOCX/MD/TXT → 纯文本）
├── splitter.py            # 文本分块（RecursiveCharacterTextSplitter）
├── vector_store.py        # Milvus 封装（基于 MilvusClient）
├── bm25.py                # BM25 关键词检索（jieba 中文分词）
├── reranker.py            # Cross-Encoder 重排（gte-rerank-v2）
├── query_rewrite.py       # Multi-Query / HyDE
├── advanced_retrieval.py  # 高级检索管道（混合 + RRF + Rerank）
├── retrieval.py           # 检索 + 生成（LCEL）
├── ingestion.py           # 入库编排
└── repository.py          # 文档元数据（内存版）
```

---

## 二、入库流水线

### 2.1 整体流程

```
[文件] → 解析 → 分块 → 批量 Embedding → Milvus 插入 → BM25 失效
```

### 2.2 解析层（parser.py）

| 格式 | 库 | 备注 |
|------|----|------|
| PDF | PyMuPDF (fitz) | 速度快、版式还原好 |
| DOCX | python-docx | 标准实现 |
| MD / TXT | 直接读 | UTF-8 |

**为什么不用 unstructured？** 它支持广但慢；做精细控制不便。我们用更轻量的方案，需要时再升级。

### 2.3 分块层（splitter.py）

**算法**：`RecursiveCharacterTextSplitter`，递归选择分隔符：

```python
CHINESE_SEPARATORS = [
    "\n\n",   # 优先按段落
    "\n",     # 再按行
    "。", "！", "？", "；",   # 中文句子
    ".", "!", "?", ";",        # 英文句子
    "，", ",", " ", "",        # 兜底
]
```

**默认参数**：
- `chunk_size = 500` 字符
- `chunk_overlap = 80` 字符（约 16%）

**为什么这个组合？**

| 维度 | 太小 (<200) | 我们 (500) | 太大 (>1000) |
|------|------------|-----------|--------------|
| 检索精度 | 高 | 高 | 中 |
| 上下文完整性 | 差 | 中 | 好 |
| 单 chunk 信息密度 | 低 | 中 | 高 |
| Embedding 成本 | 高 | 中 | 低 |

500 字符是经验最优区间，覆盖中文 1-2 段。

**为什么要重叠？**
切片可能正好把一句完整句切成两半，重叠保证语义不被截断。例如关键句在 chunk[3] 末尾时，chunk[4] 开头也包含它。

### 2.4 Embedding 层

**模型**：`text-embedding-v3`（1024 维）

**关键工程问题**：DashScope 限制每批最多 10 条文本！直接传 100 条会 400 错误。

**解决方案**：批量并发

```python
EMBEDDING_BATCH_SIZE = 10

async def _embed_in_batches(texts: list[str]) -> list[list[float]]:
    batches = [
        texts[i : i + EMBEDDING_BATCH_SIZE]
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE)
    ]
    # 并发跑所有批次，asyncio.gather 等所有完成
    results = await asyncio.gather(
        *(embedding_model.aembed_documents(b) for b in batches)
    )
    # 把 List[List[List[float]]] flatten 成 List[List[float]]
    return [v for batch in results for v in batch]
```

100 个 chunk 用串行需要 ~10 秒，并发只用 ~400 ms。

### 2.5 Milvus 写入

```python
# MilvusClient.insert 是同步的，要包 to_thread 避免阻塞
await asyncio.to_thread(
    client.insert,
    collection_name=COLLECTION_NAME,
    data=rows,
)
```

**Schema 设计**：

```
| 字段           | 类型           | 说明                          |
|----------------|----------------|-------------------------------|
| id             | VARCHAR (PK)   | 分块 ID（doc-uuid_序号_随机）  |
| embedding      | FLOAT_VECTOR   | 1024 维                       |
| content        | VARCHAR(8192)  | 原文（检索后直接拿）           |
| document_id    | VARCHAR(64)    | 所属文档                      |
| document_name  | VARCHAR(512)   | 用于引用展示                  |
| chunk_index    | INT64          | 序号                          |
```

**为什么把 content 也存进 Milvus？**
- 减少二次查询（不用再去 PostgreSQL 拉文本）
- Milvus VARCHAR 已经够用
- 代价：存储略大，但符合 KISS 原则

**索引**：
```python
index_params.add_index(
    field_name="embedding",
    index_type="HNSW",
    metric_type="COSINE",
    params={"M": 16, "efConstruction": 200},
)
```

### 2.6 BM25 索引同步

入库后必须让 BM25 失效，下次检索时重建：

```python
get_bm25_retriever().invalidate()
```

---

## 三、检索流水线

### 3.1 总图

```
question
   │
   ↓ Step 1：Query 改写（可选）
   │   ├─ Multi-Query   → ["原问题", "变体1", "变体2"]
   │   └─ HyDE          → ["原问题 + 假设答案"]
   │
   ↓ Step 2：每个 query 跑两路检索
   │   ┌──── 向量检索 (top_k=20) ────┐
   │   │                              │
   │   └──── BM25 检索 (top_k=20) ────┘
   │
   ↓ Step 3：RRF 融合
   │   按排名打分：score(d) = Σ 1/(k + rank_i)
   │   候选 ~30 条
   │
   ↓ Step 4：Reranker 精排
   │   gte-rerank-v2 (Cross-Encoder)
   │   30 → top_5
   │
   ↓ 最终 Top-K，含 final_score
```

### 3.2 配置开关（RagConfig）

```python
@dataclass
class RagConfig:
    top_k: int = 5             # 最终返回数量
    candidate_k: int = 20      # 每路粗排数量
    use_bm25: bool = True
    use_rerank: bool = True
    use_multi_query: bool = False
    multi_query_n: int = 2
    use_hyde: bool = False
    rrf_k: int = 60
```

每项优化都可独立开关，便于评估 A/B。

### 3.3 向量检索

```python
async def search(query, top_k=10, document_ids=None):
    vec = await embedding_model.aembed_query(query)
    filter_ = f"document_id in {document_ids}" if document_ids else ""
    results = await asyncio.to_thread(
        client.search,
        collection_name=COLLECTION_NAME,
        data=[vec],
        anns_field="embedding",
        search_params={"metric_type": "COSINE", "params": {"ef": 64}},
        filter=filter_,
        output_fields=["content", "document_id", "document_name", "chunk_index"],
        limit=top_k,
    )
    return [(LCDocument(...), score) for ...]
```

要点：
- `ef = 64` 是查询时的参数（HNSW 探测数，越大越准但越慢）
- `filter` 字段可选，用于"只在这几个文档里搜"

### 3.4 BM25 检索

中英文混合分词：

```python
_EN_TOKEN = re.compile(r"[A-Za-z0-9]+")

def tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = []
    last_end = 0
    for m in _EN_TOKEN.finditer(text):
        # 英文/数字之间的中文交给 jieba
        zh = text[last_end : m.start()]
        if zh.strip():
            tokens.extend(t for t in jieba.lcut(zh) if t.strip())
        tokens.append(m.group(0))
        last_end = m.end()
    # 末尾
    tokens.extend(jieba.lcut(text[last_end:]))
    return [t for t in tokens if len(t) > 1 or _EN_TOKEN.match(t)]
```

**为什么这样切？**

```
"GPT-4 的 token 是什么"
  ↓
正则: ["gpt-4", "token"]
中间: ["的"]
jieba: ["是什么"]
  ↓
最终: ["gpt-4", "的", "token", "是什么"]
```

英文/数字精确切，中文交给 jieba。

**索引在哪？**
内存版（`BM25Okapi`）：从 Milvus 拉所有分块构建。生产环境会用 Elasticsearch / OpenSearch 替代，避免内存压力。

### 3.5 RRF 融合

```python
def _rrf_fuse(rankings: list[list[Result]], k: int = 60) -> list[Result]:
    fused = {}
    for ranking in rankings:
        for rank_idx, result in enumerate(ranking):
            inc = 1.0 / (k + rank_idx + 1)  # rank 从 1 开始
            if result.chunk_id in fused:
                fused[result.chunk_id].rrf_score += inc
            else:
                result.rrf_score = inc
                fused[result.chunk_id] = result
    return sorted(fused.values(), key=lambda r: r.rrf_score, reverse=True)
```

**为什么 RRF 不用加权和？**

```
向量分数:  0.85
BM25 分数: 23.4
最终分数 = 0.7 * 0.85 + 0.3 * 23.4 = ???
```

量纲不同（向量 0~1，BM25 0~100+），归一化方式选哪个？min-max？softmax？rank-based？每个都有问题。

**RRF 用排名**：

```
rank 1 在向量路 → 1/(60+1) = 0.0164
rank 1 在 BM25 路 → 1/(60+1) = 0.0164
合并：0.0328
```

不在乎原始分数尺度，只看顺序。简单 + 稳定 + 论文证明效果好。

### 3.6 Reranker 精排

为什么不直接用 RRF 完事？因为 RRF 还是基于"两个 Bi-Encoder"的结果，精度有限。

**Cross-Encoder vs Bi-Encoder**：

```
Bi-Encoder (向量检索):
    Query  → Encoder → 向量
    Doc    → Encoder → 向量
    相似度 = cos(向量1, 向量2)
    优点: 快（向量提前算好）
    缺点: 精度有限（query 和 doc 没"对话"）

Cross-Encoder (Reranker):
    [Query + Doc] → Encoder → 相关度分数
    优点: 精度高（看到对方）
    缺点: 慢（每次要算 Q×D 次）
```

业界标准做法：粗排 Top-50 + 精排 Top-5。

**调用 gte-rerank-v2**：

```python
async def rerank(query, documents, top_n):
    payload = {
        "model": "gte-rerank-v2",
        "input": {"query": query, "documents": documents},
        "parameters": {"top_n": top_n, "return_documents": False},
    }
    res = await client.post(RERANK_API_URL, json=payload, headers=...)
    return [(r["index"], r["relevance_score"]) for r in res.json()["output"]["results"]]
```

**降级**：调用失败时返回 `[(i, 0.5) for i in ...]`，保持原序，业务不阻断。

### 3.7 Query 改写

**Multi-Query**：让 LLM 生成多个语义等价的变体

```
原: "RAG 是什么？"
改: 
  - "什么是检索增强生成？"
  - "RAG 的工作原理是怎样的？"
```

**HyDE**：让 LLM 先"幻想"答案，用答案做检索

```
原: "RAG 是什么？"
幻: "RAG 是一种结合检索与生成的技术，先从知识库检索文档..."
检索: 用幻想出来的答案做向量检索（语义更接近真实文档）
```

**两者取舍**：

| | Multi-Query | HyDE |
|---|------------|------|
| 适合 | 表述歧义大的问题 | 专业术语多的问题 |
| 延迟 | 中（多 query 检索） | 高（多一次 LLM 调用 + 检索）|
| 默认 | 关闭 | 关闭 |

→ 默认都关，遇到效果不佳的场景再开。

---

## 四、生成层

### 4.1 LCEL 链路

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", RAG_SYSTEM_PROMPT),  # 强约束（只用资料 / 找不到说不知道 / 引用编号）
    ("human", RAG_USER_PROMPT),     # context + question
])
llm = get_chat_model(temperature=0.2, streaming=True)
chain = prompt | llm | StrOutputParser()

stream = chain.astream({"context": context, "question": question})
```

### 4.2 强约束 Prompt（防幻觉）

```
你是一个严谨、专业的知识库问答助手。
【回答要求】
1. 必须基于下方提供的「参考资料」回答问题
2. 如果资料中没有相关内容，必须坦诚回答"根据已有资料无法回答这个问题"
3. 回答时要在相关句子后用 [1] [2] 这样的标号引用资料来源
4. 使用 Markdown 格式，回答简洁清晰
```

### 4.3 Context 拼装

```python
def _format_context(results):
    return "\n\n---\n\n".join(
        f"[{i+1}] 来源: {r.document_name} (相关度: {r.final_score:.3f})\n{r.content}"
        for i, r in enumerate(results)
    )
```

每段标号 `[1]` `[2]`，让 LLM 在回答中引用编号。

### 4.4 温度选择：0.2

- Chat：0.7（创造性）
- RAG：0.2（事实性）
- 太低（0）会过于死板，0.2 给一点自然语言润色空间

### 4.5 引用回溯

返回给前端的 Citation：

```python
class Citation(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    content: str          # 原文片段
    score: float          # 最终相关度
    chunk_index: int      # 在原文档中的位置
```

前端展示：每条 Citation 是可点击的卡片，点击展开原文。

---

## 五、流式协议

### 5.1 SSE 事件类型

```
event: content
data: {"content": "RAG"}

event: content
data: {"content": " 是"}

...

event: citations
data: [{"chunk_id":"...","document_name":"..."}, ...]

event: done
data: [DONE]
```

### 5.2 前端处理

```typescript
fetchEventSource('/api/v1/rag/query/stream', {
  method: 'POST',
  body: JSON.stringify({question, ...}),
  onmessage(ev) {
    if (ev.data === '[DONE]') {
      callbacks.onDone();
      return;
    }
    if (ev.event === 'citations') {
      callbacks.onCitations(JSON.parse(ev.data));
    } else {
      callbacks.onContent(JSON.parse(ev.data).content);
    }
  },
})
```

---

## 六、性能数据（实测）

| 阶段 | 单次延迟 | 备注 |
|------|---------|------|
| 文档入库（100 chunk） | ~5s | 含解析 + 分块 + 并发 Embedding |
| 向量检索 (top_20) | <100ms | HNSW + ef=64 |
| BM25 检索 (top_20) | <30ms | 内存索引 |
| RRF 融合 | <5ms | 纯 Python 字典 |
| Reranker (30 候选) | ~300ms | API 调用 |
| 端到端 RAG（首 token） | ~1.5-2s | 含全部 pipeline |

---

## 七、关键设计决策回顾

| 决策 | 选了什么 | 拒绝了什么 | 原因 |
|------|---------|-----------|------|
| Milvus 客户端 | MilvusClient（自封）| langchain-milvus | 自控 schema + 稳定 |
| 分块 | 500 字符 + 80 重叠 | 1000 / 200 | 经验最优区间 |
| Embedding 批量 | 10 / 并发 | 串行 100 | DashScope 限制 |
| 同步调用 | asyncio.to_thread | 阻塞 await | Milvus / Tavily 都是同步 SDK |
| 检索融合 | RRF | 加权和 | 免归一化 |
| 精排 | Cross-Encoder | 多次向量检索 | 业界标准 |
| Query 改写 | 默认关 | 默认开 | 延迟权衡 |
| 防幻觉 | Prompt 强约束 + 检索保底 | LLM 一招鲜 | 多层防御 |

---

## 八、踩坑速查

| 现象 | 原因 | 解决 |
|------|------|------|
| `batch size > 10` | DashScope 限制 | 批量并发 `_embed_in_batches` |
| `collection not loaded` | Milvus 重启后未 load | 启动时检查 + load |
| `index not found` | drop 后忘了重建索引 | `scripts/reset_milvus.py` |
| `LangChain Milvus connection alias` | langchain-milvus 兼容问题 | 切到原生 `MilvusClient` |
| BM25 检索拿不到新数据 | 内存索引未刷新 | 入库后调 `invalidate()` |

---

## 九、下一步阅读

- 想看 Agent 怎么调用 RAG：[05-Agent模块.md](./05-Agent模块.md)
- 想看 RAG API 详情：[06-API文档.md](./06-API文档.md)
