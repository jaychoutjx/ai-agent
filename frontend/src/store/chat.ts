/**
 * 聊天状态管理（Zustand）。
 *
 * 为什么用 Zustand 而不是 Redux/Context？
 * - 比 Redux 简单 10 倍，没有 reducer/action/dispatch 模板代码
 * - 比 Context 性能好，组件只订阅自己关心的字段，避免无关重渲染
 * - 体积小（<1kb），React 19 完美适配
 *
 * ─── 打字机流式渲染 ────────────────────────────────────────────
 * 后端 SSE 每个 chunk 不一定是单字（可能是一段，或者经过 Vercel rewrites
 * 反向代理后被聚合成大块），如果直接 append 会出现"一段一段"跳出来的
 * 视觉效果。我们引入一个 pendingBuffer + 定时器，把后端推过来的内容
 * 切成"逐字流"渲染：
 *   1. 后端 chunk 追加到 pendingBuffer
 *   2. 定时器（默认 ~25ms）从 buffer 取若干字符并 commit 到 message.content
 *   3. 速度自适应：buffer 堆积越多，每 tick 取的字符越多（避免长回答慢吞吞）
 *   4. 流结束时 flush 整个 buffer，避免丢字
 * ─────────────────────────────────────────────────────────────
 */

import { create } from "zustand";
import type { AgentToolCall, ChatMessage, Citation } from "@/lib/types";

interface ChatState {
  messages: ChatMessage[];
  isGenerating: boolean;
  abortController: AbortController | null;
  /** 待"打字机"输出的缓冲区（按 message id 分组） */
  pendingBuffer: string;
  /** 打字机定时器句柄 */
  typewriterTimer: ReturnType<typeof setInterval> | null;

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

// 打字机参数（节奏接近 ChatGPT：约每秒 25 字）
const TYPEWRITER_INTERVAL_MS = 40; // 每 40ms 推一次（每秒 25 帧）
const TYPEWRITER_MIN_CHARS = 1; // 每次至少推 1 字
const TYPEWRITER_MAX_CHARS = 3; // 堆积太多时，每次最多推 3 字（保留逐字节奏，绝不"一段一段跳"）

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isGenerating: false,
  abortController: null,
  pendingBuffer: "",
  typewriterTimer: null,

  addMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),

  /**
   * 把后端流式 chunk 入队 + 启动定时器逐字渲染（打字机效果）。
   * 后端可能一次给一个字，也可能给一大段；前端统一按"字符流"输出，体验更顺滑。
   */
  appendToLastAssistant: (chunk) => {
    if (!chunk) return;
    set((state) => ({ pendingBuffer: state.pendingBuffer + chunk }));

    if (get().typewriterTimer) return;

    const timer = setInterval(() => {
      const { pendingBuffer } = get();
      if (!pendingBuffer) return;

      // 自适应步长：buffer 堆积越多吃得越快，但封顶 MAX_CHARS 保留逐字节奏
      // - 堆积 < 150 字：每次只吐 1 字（标准打字机）
      // - 堆积 150-500：每次吐 2 字（轻微加速）
      // - 堆积 > 500：每次吐 3 字（追赶，避免长回答慢吞吞）
      const len = pendingBuffer.length;
      const step =
        len > 500
          ? TYPEWRITER_MAX_CHARS
          : len > 150
            ? 2
            : TYPEWRITER_MIN_CHARS;

      const take = pendingBuffer.slice(0, step);
      const rest = pendingBuffer.slice(step);

      set((state) => {
        const messages = [...state.messages];
        const last = messages[messages.length - 1];
        if (last && last.role === "assistant") {
          messages[messages.length - 1] = {
            ...last,
            content: last.content + take,
          };
        }
        return { messages, pendingBuffer: rest };
      });
    }, TYPEWRITER_INTERVAL_MS);

    set({ typewriterTimer: timer });
  },

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

  /**
   * 流结束：先 flush 缓冲区里剩余的字到 message.content，再停定时器、关 streaming。
   * 不能直接 set streaming=false，否则用户会看到内容"突然停在半句"。
   */
  finalizeLastAssistant: () => {
    const { pendingBuffer, typewriterTimer } = get();

    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = {
          ...last,
          content: last.content + pendingBuffer,
          streaming: false,
        };
      }
      return { messages, pendingBuffer: "" };
    });

    if (typewriterTimer) {
      clearInterval(typewriterTimer);
      set({ typewriterTimer: null });
    }
  },

  setGenerating: (v) => set({ isGenerating: v }),
  setAbortController: (c) => set({ abortController: c }),

  abort: () => {
    const c = get().abortController;
    if (c) c.abort();
    const { typewriterTimer } = get();
    if (typewriterTimer) clearInterval(typewriterTimer);
    set({
      isGenerating: false,
      abortController: null,
      typewriterTimer: null,
      pendingBuffer: "",
    });
  },

  clear: () => {
    const { typewriterTimer } = get();
    if (typewriterTimer) clearInterval(typewriterTimer);
    set({
      messages: [],
      isGenerating: false,
      typewriterTimer: null,
      pendingBuffer: "",
    });
  },
}));
