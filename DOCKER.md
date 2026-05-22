# 🐳 Docker 部署说明

本项目支持两种 Docker 编排模式：**全栈模式**（推荐）和 **基础设施模式**（开发用）。

---

## 📋 准备工作

1. **安装 Docker Desktop**（Windows / Mac）或 Docker Engine（Linux）
2. **填好 `.env` 文件**：
   - `DASHSCOPE_API_KEY`（阿里云百炼，必填）
   - `TAVILY_API_KEY`（联网搜索，可选）
3. 确保 `19530`、`8800`、`3300`、`9001` 端口未被占用

---

## 🚀 模式 A：全栈一键启动（推荐）

适合：演示、生产、给别人体验、本地完整跑。

```bash
# 启动（首次会构建镜像，约 5-10 分钟）
docker compose up -d

# 查看日志
docker compose logs -f backend
docker compose logs -f frontend

# 停止（数据保留）
docker compose down

# 重置（连同向量库数据一起清空）
docker compose down -v
```

启动后访问：
- 前端：http://localhost:3300
- 后端 API：http://localhost:8800/docs（Swagger 文档）
- MinIO 控制台：http://localhost:9001（用户名/密码：minioadmin / minioadmin）

---

## 🛠️ 模式 B：只起基础设施（本地开发用）

适合：你想在本地用 IDE 调试后端/前端，但 Milvus 还是用 Docker 跑。

```bash
# 只启动 etcd + minio + milvus
docker compose -f docker-compose.infra.yml up -d

# 然后本地启动后端
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8800

# 本地启动前端
cd frontend
pnpm dev

# 停止基础设施
docker compose -f docker-compose.infra.yml down
```

---

## 📦 镜像与体积

| 镜像 | 体积 | 说明 |
|------|------|------|
| `project-01-backend` | ~700MB | python:3.11-slim + 200+ AI 依赖 |
| `project-01-frontend` | ~180MB | Next.js standalone（精简 node_modules） |
| `milvusdb/milvus:v2.5.14` | ~1GB | 向量数据库 |
| `quay.io/coreos/etcd` | ~50MB | Milvus 元数据存储 |
| `minio/minio` | ~150MB | Milvus 对象存储 |

**总体积约 2.1GB**。后端镜像如果加上 sentence-transformers 之类大模型库会突破 5GB，所以本项目把 Embedding/Reranker 都放在云端（百炼），保持镜像精简。

---

## 🔧 常见问题

### Q1：启动后 backend 一直 Restarting
```bash
docker logs aikb-backend --tail 50
```
最常见原因：
- `.env` 中 `DASHSCOPE_API_KEY` 没填
- Milvus 还没就绪（等 30-60 秒）

### Q2：3300 端口被占用
```bash
# 找到占用进程
netstat -ano | findstr :3300

# Windows 杀进程
taskkill /F /PID <pid>
```

### Q3：想看 Milvus 里的数据
打开 MinIO 控制台 http://localhost:9001 看对象存储；或者用 [Attu](https://github.com/zilliztech/attu)（Milvus 的图形化管理工具）：
```bash
docker run -p 8000:3000 -e MILVUS_URL=host.docker.internal:19530 zilliz/attu:latest
```

### Q4：volume 在哪里？怎么备份？
```bash
# 列出本项目所有 volume
docker volume ls --filter name=project-01_

# 检查 volume 实际位置（Windows 在 WSL 里）
docker volume inspect project-01_milvus-data
```

### Q5：怎么完全清理？
```bash
# 停止 + 删除容器 + 删除 volume + 删除 network
docker compose down -v --remove-orphans

# 如果还要删镜像
docker rmi project-01-backend project-01-frontend
```

---

## 🏗️ 生产部署建议

本项目的 docker-compose 适合**单机演示**。生产部署建议：

1. **后端** → Kubernetes Deployment（多副本 + HPA 自动扩缩）
2. **Milvus** → 用 [Milvus Helm Chart](https://github.com/milvus-io/milvus-helm) 部署集群版
3. **前端** → Vercel / Cloudflare Pages（CDN 加速）
4. **网关** → Nginx / Traefik 反向代理 + HTTPS
5. **可观测性** → Langfuse + Prometheus + Grafana
6. **CI/CD** → GitHub Actions 自动构建并推送镜像到 ACR/ECR

---

## 🎯 给面试官看的话

> "项目支持 Docker Compose 一键启动全栈：5 个服务（前端/后端/Milvus/etcd/MinIO）通过 Docker network 内网通信。后端镜像采用多阶段构建（builder 装依赖 → runtime 仅拷 .venv），最终镜像 ~700MB；前端用 Next.js standalone 模式，镜像 ~180MB。生产环境可平滑迁移到 K8s + Milvus 集群版。"
