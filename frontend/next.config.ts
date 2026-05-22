import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // standalone 模式：只把运行时必需的文件（含最小化的 node_modules）输出到 .next/standalone
  // Docker 镜像可以小到 ~150MB（vs 默认的 1GB+）
  output: "standalone",

  // 后端 API 由 docker-compose 内网通信；浏览器访问的 URL 通过 NEXT_PUBLIC_API_BASE_URL 注入
  // 不在这里做 rewrites，保持架构清晰
};

export default nextConfig;
