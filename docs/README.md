# AI Knowledge Base · 技术文档

> 企业级智能知识库问答系统 · 技术文档总入口

---

## 📚 文档导航

本目录是项目的**技术文档**，按"由浅入深"的顺序组织。建议阅读顺序：

| # | 文档 | 适合谁看 | 阅读时长 |
|---|------|---------|---------|
| 01 | [项目概览](./01-项目概览.md) | 所有人（先看这个） | 5 min |
| 02 | [架构设计](./02-架构设计.md) | 开发、面试官 | 15 min |
| 03 | [技术选型](./03-技术选型.md) | 架构、面试官 | 10 min |
| 04 | [RAG 模块](./04-RAG模块.md) | 后端开发 | 20 min |
| 05 | [Agent 模块](./05-Agent模块.md) | 后端开发 | 15 min |
| 06 | [API 文档](./06-API文档.md) | 前端 / 集成方 | 10 min |
| 07 | [部署运维](./07-部署运维.md) | DevOps | 10 min |
| 08 | [开发指南](./08-开发指南.md) | 新加入的开发 | 10 min |

---

## 🎯 不同读者的"快捷路径"

### 🆕 我是新加入的开发

```
01-项目概览 → 08-开发指南 → 02-架构设计 → 04 / 05 模块文档
```

5 分钟搞清楚做什么，10 分钟把环境跑起来，剩下按需深入。

### 🎤 我是面试官 / 评审

```
01-项目概览 → 02-架构设计 → 03-技术选型 → 04-RAG 模块（重点）
```

30 分钟内掌握项目全貌 + 技术决策 + 关键实现。

### 🚀 我要部署上线

```
07-部署运维 → 06-API 文档
```

直接 `docker compose up -d`，看 7 文档处理生产化。

### 🔍 我在排查 bug

```
02-架构设计（找模块） → 对应模块文档（04 / 05 / 06）
```

---

## 📦 项目快速档案

| 维度 | 信息 |
|------|------|
| **项目名** | AI-Knowledge-Base |
| **类型** | 企业级 LLM 应用（RAG + Agent） |
| **后端** | Python 3.11 · FastAPI · LangChain 1.x · LangGraph |
| **前端** | TypeScript · Next.js 15 · React 19 · Tailwind CSS |
| **存储** | Milvus（向量）· PostgreSQL（关系，规划中）· Redis（缓存，规划中） |
| **LLM** | 阿里云百炼 Qwen 系列（qwen-plus / text-embedding-v3 / gte-rerank-v2） |
| **部署** | Docker Compose（5 服务一键启动） |
| **代码量** | 后端 ~32 个 Python 模块，前端 ~15 个 TS 模块 |
| **文档** | 本目录 8 篇 + `interview-prep/` 9 篇面试题库 |

---

## 🔑 核心特性

```
┌──────────────────────────────────────────────────┐
│  Chat 模式                                        │
│  └─ 多轮对话 + SSE 流式输出（首 token ~700ms）   │
├──────────────────────────────────────────────────┤
│  RAG 模式（知识库问答）                           │
│  ├─ 文档上传：PDF / Word / Markdown / TXT         │
│  ├─ 解析 → 切片 → Embedding → Milvus 入库        │
│  ├─ 混合检索：向量 + BM25                          │
│  ├─ RRF 融合多路结果                               │
│  ├─ Reranker 精排（gte-rerank-v2）                │
│  ├─ Query 改写：Multi-Query / HyDE（可选）        │
│  └─ 强约束 Prompt + 引用回溯                       │
├──────────────────────────────────────────────────┤
│  Agent 模式（自主推理）                           │
│  ├─ LangGraph StateGraph 编排                     │
│  ├─ 4 个工具：知识库 / Tavily 联网 / 计算 / 时间   │
│  ├─ 节点级流式（思考过程实时推送）                │
│  └─ MAX_ITERATIONS 防死循环                        │
└──────────────────────────────────────────────────┘
```

---

## 🗂 项目目录结构

```
project-01/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/            # REST API（health/chat/documents/rag/agent）
│   │   ├── core/              # 配置、日志
│   │   ├── schemas/           # Pydantic 模型
│   │   └── services/          # 业务层
│   │       ├── llm/          #   ChatModel + Embedding + LCEL chain
│   │       ├── rag/          #   parser/splitter/vector_store/retrieval/...
│   │       └── agent/        #   LangGraph state/tools/graph
│   ├── scripts/              # 测试、评估、数据脚本
│   ├── Dockerfile            # 多阶段构建（~400 MB）
│   └── pyproject.toml        # uv 依赖
├── frontend/                  # Next.js 前端
│   └── src/
│       ├── app/              # 路由（layout/page）
│       ├── components/       # chat/ + knowledge/ 组件
│       ├── lib/              # api/types/utils
│       └── store/            # Zustand 状态
├── docker-compose.yml         # 全栈编排（5 服务）
├── docker-compose.infra.yml   # 仅基础设施（开发用）
├── docs/                      # ← 你正在看的目录
└── interview-prep/            # 面试题库（9 篇）
```

---

## 🏃‍♂️ 5 分钟跑起来

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入：DASHSCOPE_API_KEY=sk-xxx

# 2. 一键启动
docker compose up -d

# 3. 访问
# 前端：http://localhost:3300
# 后端 API 文档：http://localhost:8800/docs
```

详细部署见 [07-部署运维.md](./07-部署运维.md)。

---

## 📊 性能指标（实测）

| 场景 | 指标 | 实测值 |
|------|------|--------|
| Chat 流式 | 首 token 时间 | ~700ms |
| RAG 流式 | 首 token 时间 | ~1.5-2s（含检索 + Reranker） |
| Agent 流式 | 首 token 时间 | ~2-4s（含工具调用） |
| 文档入库 | 100 chunks Embedding | ~400ms（并发批处理） |
| 向量检索 | Top-5 召回 | <100ms |
| BM25 检索 | Top-5 召回 | <30ms |
| Reranker | 30 候选重排 | ~300ms |

---

## 🤝 贡献指南

详见 [08-开发指南.md](./08-开发指南.md)。

---

## 📝 版本

- **v0.1.0** (2026-05) · MVP 完成，Docker Compose 全栈部署
