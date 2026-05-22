/**
 * 聊天状态管理（Zustand）。
 *
 * 为什么用 Zustand 而不是 Redux/Context？
 * - 比 Redux 简单 10 倍，没有 reducer/action/dispatch 模板代码
 * - 比 Context 性能好，组件只订阅自己关心的字段，避免无关重渲染
 * - 体积小（<1kb），React 19 完美适配
 */

import { create } from "zustand";
import type { AgentToolCall, ChatMessage, Citation } from "@/lib/types";

interface ChatState {
  messages: ChatMessage[];
  isGenerating: boolean;
  abortController: AbortController | null;

  addMessage: (msg: ChatMessage) => void;
  appendToLastAssistant: (chunk: string) => void;
  setLastAssistantCitations: (citations: Citation[]) => void;
  addToolCallToLastAssistant: (call: AgentToolCall) => void;
  updateToolCallResult: (tool_name: string, summary: string) => void;
  finalizeLastAssistant: () => void;
  setGenerating: (v: boolean) => void;
  setAbortController: (c: AbortController | null) => void;
  abort: () => void;
  clear: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isGenerating: false,
  abortController: null,

  addMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),

  appendToLastAssistant: (chunk) =>
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = {
          ...last,
          content: last.content + chunk,
        };
      }
      return { messages };
    }),

  setLastAssistantCitations: (citations) =>
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = { ...last, citations };
      }
      return { messages };
    }),

  addToolCallToLastAssistant: (call) =>
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        const tool_calls = [...(last.tool_calls ?? []), call];
        messages[messages.length - 1] = { ...last, tool_calls };
      }
      return { messages };
    }),

  updateToolCallResult: (tool_name, summary) =>
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant" && last.tool_calls) {
        const tool_calls = [...last.tool_calls];
        // 找最后一个相同 tool_name 且仍在 running 的
        for (let i = tool_calls.length - 1; i >= 0; i--) {
          if (
            tool_calls[i].tool_name === tool_name &&
            tool_calls[i].status === "running"
          ) {
            tool_calls[i] = {
              ...tool_calls[i],
              result_summary: summary,
              status: "done",
            };
            break;
          }
        }
        messages[messages.length - 1] = { ...last, tool_calls };
      }
      return { messages };
    }),

  finalizeLastAssistant: () =>
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = { ...last, streaming: false };
      }
      return { messages };
    }),

  setGenerating: (v) => set({ isGenerating: v }),
  setAbortController: (c) => set({ abortController: c }),

  abort: () => {
    const c = get().abortController;
    if (c) c.abort();
    set({ isGenerating: false, abortController: null });
  },

  clear: () => set({ messages: [], isGenerating: false }),
}));
