/**
 * 前端配置中心。
 * 通过 NEXT_PUBLIC_ 前缀的环境变量暴露给浏览器。
 *
 * apiBaseUrl 取值规则：
 *   - 设置 NEXT_PUBLIC_API_BASE_URL=http://x:port → 直连后端（开发/Docker 部署）
 *   - 设置 NEXT_PUBLIC_API_BASE_URL=""（空串）   → 走相对路径，如 "/api/v1/..."
 *                                                  适用于 Vercel rewrites 等同源代理场景
 *   - 不设置                                       → 默认 localhost（本地开发兜底）
 */

const envBase = process.env.NEXT_PUBLIC_API_BASE_URL;

export const config = {
  apiBaseUrl: envBase !== undefined ? envBase : "http://127.0.0.1:8800",
  appName: "AI 知识库助手",
} as const;
