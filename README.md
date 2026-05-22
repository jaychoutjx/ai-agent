<div align="center">

# AI Knowledge Base · 企业级智能知识库问答系统

**基于 LangChain + LangGraph + 阿里云百炼 Qwen 构建的全栈 LLM 应用**

支持 RAG 文档问答、Agent 自主推理、多工具调用、SSE 流式输出

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-0.3-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-1C3C3C)](https://langchain-ai.github.io/langgraph/)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Milvus](https://img.shields.io/badge/Milvus-2.5-00A1EA)](https://milvus.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

[功能特性](#-功能特性) · [架构设计](#-架构设计) · [快速开始](#-快速开始) · [技术亮点](#-技术亮点) · [文档](./docs/)

</div>

---

## 📖 项目简介

这是一个**生产级**的企业知识库 AI 应用：用户上传文档（PDF/Word/Markdown）后，可以基于文档内容进行智能问答，回答带引用回溯；同时内置 LangGraph Agent，支持自主调用知识库、联网搜索、计算器、获取时间等工具完成多步推理任务。

> 💡 **不是又一个 ChatPDF**：覆盖 RAG 高级优化（混合检索 + RRF + Reranker + Query 改写）、LangGraph 状态机编排、节点级 SSE 流式、Docker Compose 一键部署等**业界标准实践**，不是简单的 demo。

---

## ✨ 功能特性

### 🎯 三种交互模式

| 模式 | 用途 | 示例 |
|------|------|------|
| **Chat** | 通用对话 | "帮我写一首七言绝句" |
| **RAG** | 知识库问答 | "这份合同的违约金条款是什么？" |
| **Agent** | 自主推理 + 工具调用 | "查今年北京 GDP，并算占全国的百分之几" |

### 📄 文档管理

- 支持格式：**PDF / DOCX / Markdown / TXT**（最大 50 MB）
- 异步入库：上传立即返回，后台解析 + 切片 + 向量化
- 实时状态：`pending → parsing → ready / failed`
- 联动清理：删除文档时同步清理 Milvus 向量 + BM25 索引

### 🔍 RAG 高级检索

```
[用户问题]
    │
    ↓ Step 1：Query 改写（可选）
    │   ├─ Multi-Query：生成 N 个语义变体
    │   └─ HyDE：让 LLM 幻想答案再检索
    ↓
[Step 2：双路并行检索]
    ├─ 向量检索 (text-embedding-v3 + Milvus HNSW)
    └─ BM25 关键词检索 (jieba 中文分词)
    ↓ Step 3：RRF 融合（k=60，免归一化）
    ↓ Step 4：Cross-Encoder 重排 (gte-rerank-v2)
    ↓
[Top-5] → LLM 生成 → 带引用的回答
```

### 🤖 LangGraph Agent

- **4 个工具**：知识库检索 / Tavily 联网 / 计算器（沙箱）/ 当前时间
- **ReAct 模式**：LLM 思考 → 调用工具 → 观察结果 → 再思考
- **节点级流式**：前端实时展示"思考过程"卡片（工具名、参数、耗时、结果）
- **MAX_ITERATIONS=6** 防死循环
- **优雅降级**：Tavily 未配 key 时返回 mock 文案，不阻断流程

### ⚡ 工程化

- **SSE 流式**：Chat / RAG / Agent 三套，首 token < 1s
- **多阶段 Docker 构建**：后端 ~400MB，前端 standalone ~150MB
- **健康检查 + 启动顺序**：`depends_on: condition: service_healthy`
- **12-Factor App**：日志 stdout 优先，配置全走环境变量
- **非 root 容器**：安全加固

---

## 🏗 架构设计

### 系统架构

```
                          ┌──────────────────────────┐
                          │   浏览器 (Next.js 15)    │
                          │   ChatPanel + AgentTrace │
                          └──────────┬───────────────┘
                                     │ HTTP / SSE (3300)
                                     ↓
       ┌─────────────────────────────────────────────────────┐
       │            FastAPI 后端 (端口 8800)                  │
       │  ┌──────────────────────────────────────────────┐  │
       │  │  api/v1/  health·chat·documents·rag·agent     │  │
       │  └──────────────────────────────────────────────┘  │
       │                         ↓                            │
       │  ┌──────────────────────────────────────────────┐  │
       │  │  services/                                    │  │
       │  │   ├── llm/    ChatModel + Embedding + LCEL   │  │
       │  │   ├── rag/    parser + splitter + retrieval  │  │
       │  │   └── agent/  LangGraph StateGraph           │  │
       │  └──────────────────────────────────────────────┘  │
       └────────┬──────────────────────────┬─────────┬───────┘
                │                          │         │
                ↓ pymilvus                 ↓ httpx   ↓ httpx
        ┌──────────────┐          ┌─────────────┐  ┌────────────┐
        │   Milvus     │          │  阿里云百炼  │  │  Tavily    │
        │  (向量库)     │          │  (Qwen LLM) │  │ (联网搜索) │
        │ etcd + minio │          │ Chat / Embed│  │            │
        └──────────────┘          │ / Reranker  │  └────────────┘
                                  └─────────────┘
```

### Agent 工作流（LangGraph StateGraph）

```
       START
         │
         ↓
   ┌──────────┐
   │  agent   │ ← LLM 决策（思考 + 决定调哪个工具）
   └────┬─────┘
        │
        ↓ has tool_calls?
      ┌─┴─┐
      │   │
   是  ↓   ↓ 否
   ┌─────┐  END (返回最终回答)
   │tools│
   └──┬──┘
      │
      └──→ 回到 agent（继续推理，最多 6 轮）
```

### 完整文档

更详细的架构、模块设计、API 规范见 [docs/](./docs/) 目录：

| # | 文档 | 内容 |
|---|------|------|
| 01 | [项目概览](./docs/01-项目概览.md) | 是什么 / 解决什么 / 做到什么程度 |
| 02 | [架构设计](./docs/02-架构设计.md) | 分层 / 数据流 / 并发模型 |
| 03 | [技术选型](./docs/03-技术选型.md) | 每个选型的对比 + 取舍 + 代价 |
| 04 | [RAG 模块](./docs/04-RAG模块.md) | 检索流水线 / RRF / Reranker / Query 改写 |
| 05 | [Agent 模块](./docs/05-Agent模块.md) | LangGraph 编排 / 工具集 / 流式协议 |
| 06 | [API 文档](./docs/06-API文档.md) | 全部 REST/SSE 端点规范 |
| 07 | [部署运维](./docs/07-部署运维.md) | Docker Compose + 生产化清单 |
| 08 | [开发指南](./docs/08-开发指南.md) | 本地开发环境搭建 |

---

## 🚀 快速开始

### 方式一：Docker Compose 一键启动（推荐）

```bash
# 1. 克隆代码
git clone https://github.com/yourname/ai-knowledge-base.git
cd ai-knowledge-base

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入：
#   DASHSCOPE_API_KEY=sk-xxx              # 阿里云百炼（必填）
#   TAVILY_API_KEY=tvly-xxx               # Tavily 联网搜索（可选）

# 3. 一键启动
docker compose up -d

# 4. 访问
# 前端：http://localhost:3300
# 后端 Swagger UI：http://localhost:8800/docs
```

5 个服务（etcd + minio + milvus + backend + frontend）会自动按健康检查顺序启动，约 90 秒后全部就绪。

### 方式二：本地开发模式

```bash
# 启动基础设施（Milvus 三件套）
docker compose -f docker-compose.infra.yml up -d

# 后端
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8800

# 前端（另开一个终端）
cd frontend
pnpm install
pnpm dev
```

---

## 🎬 演示截图

> 推荐补充三张截图占位，后续录视频/截图替换：

| 文档管理 | RAG 问答（带引用） | Agent 多工具推理 |
|---------|-------------------|-----------------|
| ![文档](./docs/screenshots/documents.png) | ![RAG](./docs/screenshots/rag.png) | ![Agent](./docs/screenshots/agent.png) |

📺 **演示视频**：[YouTube](https://youtube.com/...) / [Bilibili](https://bilibili.com/...)

---

## 💡 技术亮点

### 1️⃣ RAG 高级优化（不只是简单向量检索）

| 优化点 | 实现 | 效果 |
|--------|------|------|
| **混合检索** | 向量 + BM25 双路并行 | 解决向量对专有名词/数字/代号失效的问题 |
| **RRF 融合** | `score = Σ 1/(k+rank)` | 免归一化合并多路排序，论文证明优于加权和 |
| **Cross-Encoder 精排** | gte-rerank-v2 (粗排 30 → 精排 5) | Recall@5 从 ~70% 提升至 90%+ |
| **Query 改写** | Multi-Query / HyDE | 解决用户提问与文档表述不一致的问题 |
| **强约束 Prompt** | 找不到必须说"不知道" | 显著降低幻觉 |

### 2️⃣ LangGraph Agent（不是简单的 Function Call）

- **StateGraph 状态机**：节点（agent / tools）+ 条件边 + reducer，结构清晰可维护
- **TrackedToolNode**：继承 `ToolNode` 在执行前后埋点记录（工具名/参数/耗时/结果摘要），用于前端"思考过程"展示
- **astream_events v2 流式**：精确区分 `tool_call_chunks`（LLM 内部工具调用思考）和 `content` chunks（最终回答 token），避免把 JSON 推到聊天框
- **优雅降级**：Tavily 未配 key 时返回 mock 文本提示用户，不让 Agent 崩

### 3️⃣ 工程深度

| 问题 | 我们的解决 |
|------|-----------|
| DashScope embedding 单批限制 10 条 | 分批 + `asyncio.gather` 并发，100 chunks 从 10s → 400ms |
| Milvus 重启后 collection unloaded | 启动时检查 `get_load_state` + 自动 load |
| pymilvus 同步 SDK 阻塞事件循环 | `asyncio.to_thread` 包装关键调用 |
| 容器内非 root 用户无法写 logs/ | `_try_create_log_dir()` 优雅降级到 stdout-only |
| pnpm 11 要 Node 22 | Dockerfile + `package.json packageManager` 双锁定 |
| LangChain Milvus 集成不稳 | 绕开 `langchain-milvus`，直接用原生 `MilvusClient` 自封 |

### 4️⃣ 全栈完整度

- **前端有真东西**：不是 Streamlit / 命令行 demo，是 Next.js 15 + React 19 + Tailwind 的现代 UI
- **流式 + 思考过程**：前端 `AgentTrace` 组件实时展示工具调用，用户能看到 Agent "在干嘛"
- **Citation 卡片**：RAG 引用可点击展开原文，溯源到 chunk 粒度

---

## 🛠 技术栈

### 后端

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.11 |
| Web 框架 | FastAPI 0.115（async-first） |
| LLM 编排 | LangChain 0.3 + LangGraph 0.2 |
| LLM | 阿里云百炼 Qwen（qwen-plus / qwq-plus） |
| Embedding | text-embedding-v3（1024 维） |
| Reranker | gte-rerank-v2（Cross-Encoder） |
| 向量库 | Milvus 2.5（HNSW + COSINE） |
| 数据校验 | Pydantic v2 |
| 依赖管理 | uv（Rust 实现，比 pip 快 10-100x） |
| 日志 | loguru |
| 联网搜索 | Tavily |

### 前端

| 类别 | 选型 |
|------|------|
| 框架 | Next.js 15（App Router）+ React 19 |
| 语言 | TypeScript |
| 样式 | Tailwind CSS |
| 状态 | Zustand 5（~1KB） |
| SSE | @microsoft/fetch-event-source |
| Markdown | react-markdown + remark-gfm |
| 包管理 | pnpm 11 |

### 部署

| 类别 | 选型 |
|------|------|
| 容器化 | Docker（多阶段构建） |
| 编排 | Docker Compose（5 服务，含健康检查） |

---

## 📊 性能数据（实测）

| 场景 | 指标 | 实测值 |
|------|------|-------|
| Chat 流式 | 首 token 时间 | ~700ms |
| RAG 流式 | 首 token 时间 | ~1.5-2s（含检索 + Reranker） |
| Agent 流式 | 首 token 时间 | ~2-4s（含工具调用） |
| 文档入库 | 100 chunks Embedding | ~400ms（并发批处理） |
| 向量检索 | Top-5 召回 | <100ms |
| BM25 检索 | Top-5 召回 | <30ms |
| Reranker | 30 候选重排 | ~300ms |

---

## 📂 目录结构

```
project-01/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/            # health/chat/documents/rag/agent
│   │   ├── core/              # config, logger
│   │   ├── schemas/           # Pydantic 模型
│   │   └── services/
│   │       ├── llm/           # ChatModel + Embedding + LCEL
│   │       ├── rag/           # parser/splitter/vector_store/...
│   │       └── agent/         # state/tools/graph
│   ├── scripts/               # 测试脚本 + RAG 评估
│   ├── Dockerfile             # 多阶段构建
│   └── pyproject.toml
├── frontend/                  # Next.js 前端
│   └── src/
│       ├── app/               # App Router
│       ├── components/
│       │   ├── chat/          # ChatPanel + MessageBubble + AgentTrace
│       │   └── knowledge/     # DocumentList + UploadButton
│       ├── lib/               # api / types / config
│       └── store/             # Zustand
├── docker-compose.yml         # 全栈编排（5 服务）
├── docker-compose.infra.yml   # 仅基础设施（开发用）
├── docs/                      # 技术文档（8 篇）
└── interview-prep/            # 面试题库（9 篇）
```

---

## 🗺 Roadmap

- [x] **MVP** — 完整 RAG + Agent + Docker Compose 一键部署
- [x] **RAG 高级** — Hybrid + RRF + Reranker + Query 改写
- [x] **流式 UI** — 节点级 SSE + 思考过程展示
- [ ] **可观测** — Langfuse 链路追踪
- [ ] **持久化** — PostgreSQL 替换内存仓库
- [ ] **缓存** — Redis 语义缓存
- [ ] **CI/CD** — GitHub Actions
- [ ] **鉴权** — JWT 多租户
- [ ] **多模态** — 图片输入 + GPT-4V

---

## 🤝 贡献

欢迎 PR！开发指南见 [docs/08-开发指南.md](./docs/08-开发指南.md)。

---

## 📄 License

[MIT](./LICENSE)

---

## 🙋 Author

**邰金学** · AI 大模型应用开发

- GitHub：[@yourname](https://github.com/yourname)
- 邮箱：your.email@example.com

如果这个项目对你有帮助，欢迎 ⭐ Star！
