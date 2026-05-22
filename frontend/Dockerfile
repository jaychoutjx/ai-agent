# =============================================================
# 前端镜像（Next.js 16 + React 19）
#
# 三阶段构建策略：
# 1. deps:    只装依赖（独立缓存层）
# 2. builder: 拷代码 + build，产出 .next/standalone
# 3. runner:  极简运行时（仅 Node.js + standalone 产物）
#
# 镜像大小：~180MB（vs 全量 ~1.5GB，瘦身 88%）
# =============================================================

ARG NODE_VERSION=22-alpine

# ============== Stage 1: deps ==============
FROM node:${NODE_VERSION} AS deps

# Alpine 装 libc 兼容层（某些 native 包需要）
RUN apk add --no-cache libc6-compat

WORKDIR /app

# 启用 corepack 以使用 pnpm（与本地开发保持一致）
RUN corepack enable

COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml* ./
RUN pnpm install --frozen-lockfile

# ============== Stage 2: builder ==============
FROM node:${NODE_VERSION} AS builder

WORKDIR /app
RUN corepack enable

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
# 给前端一个默认的 API 地址（构建期注入；运行时还可以通过环境变量覆盖）
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8800
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

RUN pnpm build

# ============== Stage 3: runner ==============
FROM node:${NODE_VERSION} AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3300 \
    HOSTNAME=0.0.0.0

# 非 root 用户
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

# 拷贝 standalone 产物（自带最小化 node_modules）
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3300

# standalone 模式自动生成 server.js
CMD ["node", "server.js"]
