import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 知识库助手",
  description: "基于 LangChain + LangGraph + 通义千问的企业级智能知识库问答系统",
};

// 移动端必备：让浏览器以设备真实宽度渲染（否则手机会按 980px 缩小，导致文字挤压成 1 列）
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="h-full bg-gray-50 text-gray-900">{children}</body>
    </html>
  );
}
