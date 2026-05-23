import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // standalone 模式：只把运行时必需的文件（含最小化的 node_modules）输出到 .next/standalone
  // 适用于 Docker 自部署（镜像可小到 ~150MB，vs 默认的 1GB+）
  // Vercel 部署时不要开（Vercel 有自己的部署逻辑，standalone 会导致 404）
  // 通过环境变量控制：NEXT_OUTPUT_MODE=standalone 时才启用
  ...(process.env.NEXT_OUTPUT_MODE === "standalone"
    ? { output: "standalone" as const }
    : {}),

  // 后端 API 由 docker-compose 内网通信；浏览器访问的 URL 通过 NEXT_PUBLIC_API_BASE_URL 注入
  // 不在这里做 rewrites，保持架构清晰
};

export default nextConfig;
