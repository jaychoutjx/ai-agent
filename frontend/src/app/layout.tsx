import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 知识库助手",
  description: "基于 LangChain + LangGraph + DeepSeek 的企业级智能知识库问答系统",
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
