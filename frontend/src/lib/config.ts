/**
 * 前端配置中心。
 * 通过 NEXT_PUBLIC_ 前缀的环境变量暴露给浏览器。
 */

export const config = {
  apiBaseUrl:
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8800",
  appName: "AI 知识库助手",
} as const;
