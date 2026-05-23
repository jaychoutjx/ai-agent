# =============================================================
# 后端镜像（FastAPI + LangChain + Milvus 客户端）
#
# 设计要点：
# 1. 多阶段构建：builder 阶段用完整 uv 装依赖，runtime 阶段只拷必要文件
# 2. python:3.11-slim 比 python:3.11 小 60%（仅 ~50MB）
# 3. 依赖层与代码层分开：改代码不重装依赖（利用 Docker 缓存）
# 4. 非 root 用户运行（生产安全规范）
# =============================================================

# ============== Stage 1: builder（装依赖） ==============
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 把 Debian 官方源换成阿里云镜像（中国大陆部署关键优化，速度提升 50-100 倍）
# Debian 12 用 sources.list，Debian 13 (trixie) 用 deb822 格式
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g; s|http://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g; s|http://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.6.13 /uv /usr/local/bin/uv

WORKDIR /app

# 先只拷依赖描述文件 → 装依赖 → 缓存这一层
# pyproject.toml 中 [tool.uv] package=false，所以 uv sync 只装依赖，不打包项目本身
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# 再拷代码（代码改动不会让上面的依赖层失效）
COPY app ./app
COPY scripts ./scripts

# ============== Stage 2: runtime（最小镜像） ==============
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# 创建非 root 用户
RUN groupadd -r app && useradd -r -g app -d /app app

WORKDIR /app

# 从 builder 拷贝已构建好的 venv + 代码
COPY --from=builder --chown=app:app /app /app

# 上传文件目录（会被 docker-compose 挂载为 volume）
RUN mkdir -p /app/uploads /app/data && chown -R app:app /app/uploads /app/data

USER app

EXPOSE 8800

# 健康检查（K8s/Compose 据此判断容器是否就绪）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8800/api/v1/health', timeout=3)" || exit 1

# 默认用 uvicorn 启动；生产可换成 gunicorn + uvicorn workers
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8800"]
