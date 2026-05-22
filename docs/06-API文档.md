# 06 · API 文档

> 后端所有 REST / SSE 端点的详细规范。前端 / 集成方对照本文即可。

---

## 一、通用约定

### 1.1 Base URL

| 环境 | URL |
|------|-----|
| 本地开发 | `http://localhost:8800` |
| Docker | `http://localhost:8800` |
| 生产（自己换） | `https://your-domain/` |

API 全部前缀：`/api/v1`

### 1.2 Swagger UI

启动后端后访问 [http://localhost:8800/docs](http://localhost:8800/docs)，所有端点可在线试。

### 1.3 错误响应

```json
{
  "detail": "错误描述"
}
```

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误（Pydantic 校验失败） |
| 404 | 资源不存在 |
| 413 | 上传文件过大 |
| 422 | Pydantic 校验细节 |
| 500 | 服务端异常（看日志） |

### 1.4 SSE 事件协议

所有流式接口都是 `text/event-stream`：

```
data: {"type": "...", ...}\n\n
data: [DONE]\n\n
```

错误事件：
```
data: {"type": "error", "error": "msg"}
```

---

## 二、健康检查

### `GET /api/v1/health`

```json
{
  "status": "ok",
  "service": "AI-Knowledge-Base",
  "env": "development"
}
```

用途：Docker `healthcheck` / 负载均衡探测。

---

## 三、Chat（通用对话）

### 3.1 非流式

`POST /api/v1/chat/completions`

```json
// 请求
{
  "message": "你好",
  "history": [
    {"role": "user", "content": "之前问的问题"},
    {"role": "assistant", "content": "之前的回答"}
  ]
}

// 响应
{
  "content": "你好！",
  "model": "qwen-plus"
}
```

### 3.2 流式

`POST /api/v1/chat/completions/stream`

请求同上。响应 SSE：

```
data: {"content": "你"}
data: {"content": "好"}
data: {"content": "！"}
data: [DONE]
```

错误：
```
data: {"error": "..."}
```

---

## 四、Documents（文档管理）

### 4.1 上传

`POST /api/v1/documents/upload`

`multipart/form-data`：

```
file: [二进制文件]
```

支持格式：`.pdf`、`.docx`、`.md`、`.txt`
单文件上限：`50 MB`

返回 `202 Accepted`：

```json
{
  "document": {
    "id": "abc123def456...",
    "filename": "产品手册.pdf",
    "file_type": "pdf",
    "file_size": 1234567,
    "status": "pending",
    "chunk_count": 0,
    "uploaded_at": "2026-05-15T20:32:00",
    "error_message": null
  }
}
```

> 后台异步处理（解析 → 分块 → Embedding → Milvus），前端轮询查状态。

### 4.2 列表

`GET /api/v1/documents`

```json
{
  "total": 3,
  "documents": [
    {"id": "...", "filename": "...", "status": "ready", "chunk_count": 42, ...},
    ...
  ]
}
```

### 4.3 单个

`GET /api/v1/documents/{doc_id}`

```json
{
  "id": "...",
  "filename": "...",
  "status": "ready",
  "chunk_count": 42,
  "uploaded_at": "...",
  "error_message": null
}
```

`status` 枚举：

| 值 | 含义 |
|----|------|
| `pending` | 已收到，等待处理 |
| `parsing` | 解析 + 入库中 |
| `ready` | 就绪，可检索 |
| `failed` | 失败（看 `error_message`）|

### 4.4 删除

`DELETE /api/v1/documents/{doc_id}` → `204 No Content`

会同步清理：
- Milvus 里所有 chunk
- 触发 BM25 索引失效
- 删除上传目录中的源文件

---

## 五、RAG（知识库问答）

### 5.1 请求体（共用）

```typescript
interface RagQueryRequest {
  question: string;            // 用户问题
  top_k?: number;              // 默认 5
  document_ids?: string[];     // 限定检索的文档；不传 = 全库
  use_bm25?: boolean;          // 默认 true
  use_rerank?: boolean;        // 默认 true
  use_multi_query?: boolean;   // 默认 false
  use_hyde?: boolean;          // 默认 false
}
```

### 5.2 非流式

`POST /api/v1/rag/query`

```json
// 响应
{
  "answer": "RAG 是检索增强生成 [1]，它通过先检索相关文档[2]再让 LLM 生成回答的方式...",
  "citations": [
    {
      "chunk_id": "doc-uuid_0_xxx",
      "document_id": "abc123",
      "document_name": "RAG 入门.pdf",
      "content": "RAG（Retrieval-Augmented Generation）是一种...",
      "score": 0.92,
      "chunk_index": 0
    },
    ...
  ],
  "model": "qwen-plus"
}
```

### 5.3 流式

`POST /api/v1/rag/query/stream`

事件序列：

```
data: {"type":"citations","citations":[...]}     # 1) 立刻推引用
data: {"type":"content","content":"RAG"}         # 2) LLM 流式
data: {"type":"content","content":" 是"}
data: {"type":"content","content":"..."}
data: [DONE]
```

> Citations 先于内容推送，前端可以同时展示"参考资料卡片"和正在打字的回答。

---

## 六、Agent（自主推理）

### 6.1 请求体

```typescript
interface AgentRequest {
  question: string;            // 用户问题
  history?: ChatMessage[];     // 历史对话
  document_ids?: string[];     // 知识库工具的限定范围
}
```

### 6.2 流式（仅此一个端点）

`POST /api/v1/agent/run/stream`

事件序列示例（多工具串联）：

```
data: {"type":"step","node":"agent"}                                          # Agent 开始思考
data: {"type":"tool_call","tool_name":"search_knowledge_base","arguments":{"query":"..."}}
data: {"type":"step","node":"tools"}                                          # 工具执行
data: {"type":"tool_result","tool_name":"search_knowledge_base","summary":"..."}
data: {"type":"step","node":"agent"}                                          # Agent 第二轮
data: {"type":"tool_call","tool_name":"calculator","arguments":{"expression":"..."}}
data: {"type":"tool_result","tool_name":"calculator","summary":"..."}
data: {"type":"step","node":"agent"}                                          # Agent 综合
data: {"type":"content","content":"基于"}                                     # 最终回答流式
data: {"type":"content","content":"知识"}
data: {"type":"content","content":"库..."}
data: {"type":"citations","citations":[...]}                                  # 如果用过 RAG 工具
data: [DONE]
```

### 6.3 事件类型

| `type` | 字段 | 说明 |
|--------|------|------|
| `step` | `node`: "agent" \| "tools" | 节点开始 |
| `tool_call` | `tool_name`, `arguments` | LLM 决定调一个工具 |
| `tool_result` | `tool_name`, `summary` | 工具执行完，前 200 字摘要 |
| `content` | `content` | 最终回答的 token |
| `citations` | `citations: Citation[]` | RAG 工具收集的引用 |
| `error` | `error` | 错误 |

---

## 七、TypeScript 类型（与后端对齐）

```typescript
// 共享类型
interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[];
  tool_calls?: AgentToolCall[];
}

interface Citation {
  chunk_id: string;
  document_id: string;
  document_name: string;
  content: string;
  score: number;
  chunk_index: number;
}

interface AgentToolCall {
  id: string;
  tool_name: string;
  arguments: Record<string, any>;
  result_summary?: string;
  status: "running" | "done" | "error";
  duration_ms?: number;
}

// 各请求/响应 schema 见上方各端点
```

---

## 八、调用示例

### 8.1 cURL

**Chat 非流式：**

```bash
curl -X POST http://localhost:8800/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"message":"你好"}'
```

**RAG 流式：**

```bash
curl -N -X POST http://localhost:8800/api/v1/rag/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"RAG 是什么？","top_k":5}'
```

**Agent 流式：**

```bash
curl -N -X POST http://localhost:8800/api/v1/agent/run/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"现在几点？"}'
```

**上传文档：**

```bash
curl -X POST http://localhost:8800/api/v1/documents/upload \
  -F "file=@/path/to/your.pdf"
```

### 8.2 TypeScript（fetch-event-source）

```typescript
import { fetchEventSource } from '@microsoft/fetch-event-source';

await fetchEventSource('http://localhost:8800/api/v1/agent/run/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ question, history, document_ids: docIds }),
  
  onmessage(ev) {
    if (ev.data === '[DONE]') return;
    const event = JSON.parse(ev.data);
    
    switch (event.type) {
      case 'step':         setStatus(event.node); break;
      case 'tool_call':    addToolCall(event); break;
      case 'tool_result':  updateToolResult(event); break;
      case 'content':      appendContent(event.content); break;
      case 'citations':    setCitations(event.citations); break;
      case 'error':        setError(event.error); break;
    }
  },
  
  onerror(err) { throw err; },  // 否则会自动重连
});
```

### 8.3 Python（同步）

```python
import requests
import json

# 非流式 RAG
res = requests.post(
    "http://localhost:8800/api/v1/rag/query",
    json={"question": "...", "top_k": 5},
)
print(res.json())

# 流式 Agent
with requests.post(
    "http://localhost:8800/api/v1/agent/run/stream",
    json={"question": "..."},
    stream=True,
) as r:
    for line in r.iter_lines():
        if line and line.startswith(b"data: "):
            payload = line[6:].decode()
            if payload == "[DONE]":
                break
            print(json.loads(payload))
```

---

## 九、常见问题

### Q1. 为什么用 SSE 不用 WebSocket？

| | SSE | WebSocket |
|---|-----|-----------|
| 协议 | HTTP 单向 | 全双工 |
| 自动重连 | ✅ 浏览器原生 | ❌ 自己实现 |
| 防火墙穿透 | ✅ 走 HTTP | ⚠️ 部分代理不友好 |
| 实现复杂度 | 低 | 中 |
| 适合 | LLM 流式 / 通知 | 双向交互（聊天室） |

LLM 是单向（服务端推 token，客户端接收），SSE 是首选。

### Q2. 为什么前端要发 POST 而不是 GET（SSE 默认是 GET）？

需要把 history / document_ids 等大对象发给服务端，URL 装不下。

→ 用 `@microsoft/fetch-event-source` 而不是原生 `EventSource`，它支持 POST。

### Q3. 文档上传为什么是 202 不是 200？

入库要 5-30 秒，HTTP 不能让用户等这么久。返回 202 + 文档 id，前端轮询 `GET /documents/{id}` 看 `status` 字段。

### Q4. SSE 连接怎么取消？

前端用 `AbortController`：

```typescript
const ctrl = new AbortController();
fetchEventSource(url, { signal: ctrl.signal, ... });
// 取消时
ctrl.abort();
```

后端 FastAPI 会感知到客户端断开，自动停止生成。

### Q5. 速率限制 / 鉴权？

当前 v1 未实现：
- 无鉴权（默认 CORS 白名单）
- 无 rate limit

生产化方案：
- 接入 JWT（已预留 `jwt_secret_key` 配置）
- 接入 Slowapi 做 rate limit
- API Gateway 层（Kong / Traefik）

---

## 十、下一步阅读

- 想知道怎么部署起来：[07-部署运维.md](./07-部署运维.md)
- 想看怎么本地开发：[08-开发指南.md](./08-开发指南.md)
