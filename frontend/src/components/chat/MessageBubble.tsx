"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Bot, Loader2, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { Citations } from "./Citations";
import { AgentTrace } from "./AgentTrace";
import type { ChatMessage } from "@/lib/types";

import "highlight.js/styles/github-dark.css";

interface Props {
  message: ChatMessage;
}

/**
 * "AI 正在思考"占位组件。
 * 在 streaming=true 且还没有任何文本/工具调用时显示，避免出现 1-2 秒的视觉空白。
 */
function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 text-sm text-gray-500">
      <Loader2 size={14} className="animate-spin text-purple-500" />
      <span>AI 正在思考</span>
      <span className="inline-flex gap-0.5">
        <span className="h-1 w-1 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
        <span className="h-1 w-1 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
        <span className="h-1 w-1 animate-bounce rounded-full bg-gray-400" />
      </span>
    </div>
  );
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const hasCitations = !isUser && (message.citations?.length ?? 0) > 0;
  const hasToolCalls = !isUser && (message.tool_calls?.length ?? 0) > 0;
  // 流式但还没有任何内容（且没在调工具）时，显示 "正在思考" 占位
  const showThinking =
    !isUser && message.streaming && !message.content && !hasToolCalls;

  return (
    <div
      className={cn(
        "flex gap-2 px-3 py-4 sm:gap-3 sm:px-4 sm:py-5",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-blue-500 text-white"
            : "bg-gradient-to-br from-purple-500 to-pink-500 text-white",
        )}
      >
        {isUser ? <User size={18} /> : <Bot size={18} />}
      </div>

      <div
        className={cn(
          "min-w-0 max-w-[85%] sm:max-w-[75%]",
          isUser ? "items-end" : "items-start",
        )}
      >
        {hasToolCalls && <AgentTrace toolCalls={message.tool_calls!} />}
        <div
          className={cn(
            "rounded-2xl px-4 py-3 text-sm leading-relaxed",
            isUser
              ? "bg-blue-500 text-white"
              : "bg-white text-gray-900 shadow-sm ring-1 ring-gray-200",
            // Agent 还在调工具且没出文本时，隐藏空气泡（避免视觉冗余）
            !isUser &&
              !message.content &&
              hasToolCalls &&
              message.streaming &&
              "hidden",
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : showThinking ? (
            // 流式中、还没出第一个 token 时显示"正在思考"占位
            <ThinkingIndicator />
          ) : (
            <div className="prose prose-sm max-w-none break-words">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {message.content}
              </ReactMarkdown>
              {message.streaming && message.content && (
                <span className="inline-block animate-pulse">▍</span>
              )}
            </div>
          )}
        </div>

        {hasCitations && <Citations citations={message.citations!} />}
      </div>
    </div>
  );
}
