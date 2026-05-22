"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpen, MessageSquare, Sparkles, Trash2, Wrench } from "lucide-react";
import { useChatStore } from "@/store/chat";
import { useKnowledgeStore } from "@/store/knowledge";
import { streamAgent, streamChat, streamRag } from "@/lib/api";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { KnowledgeSidebar } from "@/components/knowledge/KnowledgeSidebar";
import { RagSettingsPanel } from "@/components/knowledge/RagSettings";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";

const SUGGESTIONS_CHAT = [
  "用通俗的话给我讲讲什么是 RAG",
  "Python 里 async/await 的执行原理",
  "帮我写一个快速排序的 Python 实现",
  "如何准备 AI 应用开发岗位的面试",
];

const SUGGESTIONS_RAG = [
  "总结一下我刚上传文档的核心内容",
  "文档里提到了哪些关键概念？",
  "请基于知识库回答这个问题：……",
  "对比文档中不同章节的观点",
];

const SUGGESTIONS_AGENT = [
  "现在是几点？再过 3 小时 25 分钟是几点？",
  "(123 + 456) × 789 等于多少？",
  "我的知识库里有什么内容？总结一下。",
  "今年是哪一年？这一年到现在过了多少天？",
];

export function ChatPanel() {
  const messages = useChatStore((s) => s.messages);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const addMessage = useChatStore((s) => s.addMessage);
  const appendToLastAssistant = useChatStore((s) => s.appendToLastAssistant);
  const setLastAssistantCitations = useChatStore(
    (s) => s.setLastAssistantCitations,
  );
  const addToolCall = useChatStore((s) => s.addToolCallToLastAssistant);
  const updateToolCallResult = useChatStore((s) => s.updateToolCallResult);
  const finalizeLastAssistant = useChatStore((s) => s.finalizeLastAssistant);
  const setGenerating = useChatStore((s) => s.setGenerating);
  const setAbortController = useChatStore((s) => s.setAbortController);
  const abort = useChatStore((s) => s.abort);
  const clear = useChatStore((s) => s.clear);

  const mode = useKnowledgeStore((s) => s.mode);
  const setMode = useKnowledgeStore((s) => s.setMode);
  const selectedDocIds = useKnowledgeStore((s) => s.selectedDocIds);
  const documents = useKnowledgeStore((s) => s.documents);
  const ragSettings = useKnowledgeStore((s) => s.ragSettings);

  const [showSidebar, setShowSidebar] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const handleSend = async (text: string) => {
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      createdAt: Date.now(),
    };
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      streaming: true,
      createdAt: Date.now(),
    };

    addMessage(userMsg);
    addMessage(assistantMsg);

    const history = messages.map((m) => ({ role: m.role, content: m.content }));

    const ac = new AbortController();
    setAbortController(ac);
    setGenerating(true);

    try {
      if (mode === "agent") {
        await streamAgent(
          {
            question: text,
            history,
            document_ids:
              selectedDocIds.size > 0 ? Array.from(selectedDocIds) : null,
            stream: true,
          },
          ac.signal,
          {
            onToolCall: (tool_name, args) =>
              addToolCall({
                id: crypto.randomUUID(),
                tool_name,
                arguments: args,
                status: "running",
              }),
            onToolResult: (tool_name, summary) =>
              updateToolCallResult(tool_name, summary),
            onCitations: (citations) => setLastAssistantCitations(citations),
            onContent: (chunk) => appendToLastAssistant(chunk),
            onDone: () => {
              finalizeLastAssistant();
              setGenerating(false);
              setAbortController(null);
            },
            onError: (err) => {
              appendToLastAssistant(`\n\n❌ 出错了：${err.message}`);
              finalizeLastAssistant();
              setGenerating(false);
              setAbortController(null);
            },
          },
        );
      } else if (mode === "rag") {
        await streamRag(
          {
            question: text,
            top_k: ragSettings.top_k,
            document_ids:
              selectedDocIds.size > 0 ? Array.from(selectedDocIds) : null,
            history,
            stream: true,
            use_bm25: ragSettings.use_bm25,
            use_rerank: ragSettings.use_rerank,
            use_multi_query: ragSettings.use_multi_query,
            use_hyde: ragSettings.use_hyde,
          },
          ac.signal,
          {
            onCitations: (citations) => setLastAssistantCitations(citations),
            onContent: (chunk) => appendToLastAssistant(chunk),
            onDone: () => {
              finalizeLastAssistant();
              setGenerating(false);
              setAbortController(null);
            },
            onError: (err) => {
              appendToLastAssistant(`\n\n❌ 出错了：${err.message}`);
              finalizeLastAssistant();
              setGenerating(false);
              setAbortController(null);
            },
          },
        );
      } else {
        await streamChat(
          { message: text, history, stream: true },
          ac.signal,
          {
            onContent: (chunk) => appendToLastAssistant(chunk),
            onDone: () => {
              finalizeLastAssistant();
              setGenerating(false);
              setAbortController(null);
            },
            onError: (err) => {
              appendToLastAssistant(`\n\n❌ 出错了：${err.message}`);
              finalizeLastAssistant();
              setGenerating(false);
              setAbortController(null);
            },
          },
        );
      }
    } catch {
      // 错误已在 onError 中处理
    }
  };

  const showWelcome = messages.length === 0;
  const isRag = mode === "rag";
  const isAgent = mode === "agent";
  const suggestions = isAgent
    ? SUGGESTIONS_AGENT
    : isRag
      ? SUGGESTIONS_RAG
      : SUGGESTIONS_CHAT;
  const readyDocCount = documents.filter((d) => d.status === "ready").length;

  return (
    <div className="flex h-full bg-gray-50">
      {showSidebar && <KnowledgeSidebar onClose={() => setShowSidebar(false)} />}

      <div className="flex h-full flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowSidebar((v) => !v)}
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition",
                showSidebar
                  ? "bg-purple-100 text-purple-700"
                  : "text-gray-600 hover:bg-gray-100",
              )}
              title="知识库"
            >
              <BookOpen size={16} />
              知识库 ({readyDocCount})
            </button>

            <Sparkles className="text-purple-500" size={22} />
            <h1 className="text-lg font-semibold text-gray-900">
              AI 知识库助手
            </h1>
            <span className="rounded-full bg-purple-100 px-2 py-0.5 text-xs text-purple-700">
              通义千问
            </span>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center rounded-lg bg-gray-100 p-0.5">
              <button
                onClick={() => setMode("chat")}
                className={cn(
                  "flex items-center gap-1 rounded px-3 py-1 text-xs transition",
                  mode === "chat"
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-600 hover:text-gray-900",
                )}
              >
                <MessageSquare size={12} />
                普通对话
              </button>
              <button
                onClick={() => setMode("rag")}
                className={cn(
                  "flex items-center gap-1 rounded px-3 py-1 text-xs transition",
                  mode === "rag"
                    ? "bg-white text-purple-700 shadow-sm"
                    : "text-gray-600 hover:text-gray-900",
                )}
              >
                <BookOpen size={12} />
                知识库问答
              </button>
              <button
                onClick={() => setMode("agent")}
                className={cn(
                  "flex items-center gap-1 rounded px-3 py-1 text-xs transition",
                  mode === "agent"
                    ? "bg-white text-orange-600 shadow-sm"
                    : "text-gray-600 hover:text-gray-900",
                )}
              >
                <Wrench size={12} />
                Agent
              </button>
            </div>

            {isRag && <RagSettingsPanel />}

            {messages.length > 0 && (
              <button
                onClick={clear}
                className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm text-gray-600 transition hover:bg-gray-100"
              >
                <Trash2 size={16} />
                清空
              </button>
            )}
          </div>
        </header>

        {isRag && (
          <div className="border-b border-purple-100 bg-purple-50 px-6 py-2 text-xs text-purple-800">
            <BookOpen className="mr-1 inline" size={12} />
            知识库模式
            {selectedDocIds.size > 0
              ? ` · 限定 ${selectedDocIds.size} 篇文档`
              : ` · 全库检索（${readyDocCount} 篇）`}
            <span className="ml-3 text-purple-600">
              · Top-{ragSettings.top_k}
              {ragSettings.use_bm25 && " · BM25"}
              {ragSettings.use_rerank && " · Rerank"}
              {ragSettings.use_multi_query && " · MultiQuery"}
              {ragSettings.use_hyde && " · HyDE"}
            </span>
          </div>
        )}

        {isAgent && (
          <div className="border-b border-orange-100 bg-orange-50 px-6 py-2 text-xs text-orange-800">
            <Wrench className="mr-1 inline" size={12} />
            Agent 模式 · 可调用工具：知识库检索 / 联网搜索 / 计算器 / 时间
            {selectedDocIds.size > 0 &&
              ` · 限定 ${selectedDocIds.size} 篇文档`}
          </div>
        )}

        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          {showWelcome ? (
            <div className="flex h-full flex-col items-center justify-center px-4 text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-purple-500 to-pink-500 text-white">
                <Sparkles size={32} />
              </div>
              <h2 className="mb-2 text-2xl font-bold text-gray-900">
                {isAgent
                  ? "Agent 智能体模式"
                  : isRag
                    ? "知识库问答模式"
                    : "你好，我是小智"}
              </h2>
              <p className="mb-8 text-gray-500">
                {isAgent
                  ? "AI 自主决策，调用工具完成复杂任务（基于 LangGraph）"
                  : isRag
                    ? "基于你上传的文档，给出精准回答 + 引用来源"
                    : "基于通义千问 + LangChain，帮你解答各种问题"}
              </p>
              <div className="grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => handleSend(s)}
                    className="rounded-xl border border-gray-200 bg-white px-4 py-3 text-left text-sm text-gray-700 transition hover:border-purple-300 hover:shadow-sm"
                  >
                    {s}
                  </button>
                ))}
              </div>
              {(isRag || isAgent) && readyDocCount === 0 && (
                <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                  💡 {isAgent
                    ? "上传文档后，Agent 也能调用知识库检索工具"
                    : "知识库还是空的，先点左上角\"知识库\"按钮上传一份文档吧"}
                </div>
              )}
            </div>
          ) : (
            <div className="mx-auto max-w-3xl">
              {messages.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}
            </div>
          )}
        </div>

        <ChatInput
          onSend={handleSend}
          onStop={abort}
          isGenerating={isGenerating}
        />
      </div>
    </div>
  );
}
