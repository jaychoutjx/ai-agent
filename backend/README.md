# AI 知识库后端

基于 FastAPI + LangChain + LangGraph 的企业级智能知识库问答系统后端。

## 技术栈

- **包管理**: uv（Rust 实现，比 pip 快 10-100 倍）
- **Web 框架**: FastAPI 0.136
- **大模型**: 阿里云百炼 Qwen 系列（qwen-plus / qwq-plus）
- **Embedding**: text-embedding-v3（1024 维）
- **AI 框架**: LangChain 1.3 + LangGraph 1.2
- **可观测性**: Langfuse 4.6
- **向量库**: Milvus 2.6
- **关系库**: PostgreSQL + SQLAlchemy 2.0
- **缓存**: Redis

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

复制根目录的 `.env.example` 为 `.env`，填入：
- `DASHSCOPE_API_KEY`: https://bailian.console.aliyun.com 创建获取
  （一个 Key 即可访问 Qwen Chat / Embedding / Reranker 全系列）

### 3. 启动开发服务器

```bash
uv run uvicorn app.main:app --reload
```

访问：
- API 文档: http://localhost:8800/docs
- 健康检查: http://localhost:8800/api/v1/health

## 目录结构

```
backend/
├── app/
│   ├── api/v1/          # API 路由层
│   ├── core/            # 核心配置（config、logger）
│   ├── services/        # 业务服务层
│   │   ├── llm/         # 大模型封装
│   │   ├── rag/         # RAG 检索增强
│   │   └── agent/       # LangGraph Agent
│   ├── schemas/         # Pydantic 数据模型
│   ├── models/          # SQLAlchemy ORM 模型
│   ├── db/              # 数据库连接
│   └── utils/           # 工具函数
├── tests/               # 测试
├── scripts/             # 脚本
└── pyproject.toml       # 项目配置
```

## 开发命令

```bash
uv add <package>           # 添加依赖
uv add --dev <package>     # 添加开发依赖
uv run pytest              # 运行测试
uv run ruff check .        # 代码检查
uv run ruff format .       # 代码格式化
```
