/**
 * 前端配置中心。
 * 通过 NEXT_PUBLIC_ 前缀的环境变量暴露给浏览器。
 *
 * apiBaseUrl 取值规则：
 *   - 浏览器端（生产）: 永远走相对路径 ""，
 *                       由 Vercel rewrites 转发到 ECS 后端，避免 Mixed Content。
 *   - 服务端（SSR）   : 用 NEXT_PUBLIC_API_BASE_URL 或回落 localhost
 *                       （SSR 阶段不会被浏览器 Mixed Content 拦截）
 *   - 本地开发        : 设 NEXT_PUBLIC_API_BASE_URL=http://localhost:8800 即可
 */

function resolveApiBaseUrl(): string {
  // 浏览器端：永远同源（rewrites 处理），彻底规避 Mixed Content
  // 即使环境变量设了绝对 URL，浏览器端也忽略，强制走相对路径
  if (typeof window !== "undefined") {
    // 本地 dev 时，前端通常跑在 3300，后端在 8800，需要绝对路径
    if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
      return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8800";
    }
    return "";
  }
  // 服务端
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8800";
}

export const config = {
  apiBaseUrl: resolveApiBaseUrl(),
  appName: "AI 知识库助手",
} as const;
